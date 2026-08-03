import json
from decimal import Decimal

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt

from erpnext.controllers.item_variant import create_variant, generate_keyed_value_combinations, get_variant


DEFAULT_VARIANT_ATTRIBUTE = "Brand"
MAX_PREVIEW_ROWS = 5000
SYNC_CREATE_LIMIT = 20
MAX_CREATE_ROWS = 500


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = get_columns()
	rows = VariantCoverageReport(filters).get_rows()
	return columns, rows


@frappe.whitelist()
def create_missing_variants(filters=None, use_template_image=False):
	filters = parse_filters(filters)
	use_template_image = cint(use_template_image)

	if not frappe.has_permission("Item", "create"):
		frappe.throw(_("Not permitted to create Item variants."))

	report = VariantCoverageReport(filters)
	missing_rows = report.get_missing_rows(limit=SYNC_CREATE_LIMIT + 1)

	if len(missing_rows) > SYNC_CREATE_LIMIT:
		frappe.throw(
			_("Please narrow the filters. Synchronous creation can create up to {0} variants at a time.").format(
				SYNC_CREATE_LIMIT
			)
		)

	if not missing_rows:
		return {"created": 0, "skipped": 0, "queued": 0}

	return create_missing_variants_job(
		filters=dict(filters),
		use_template_image=use_template_image,
		limit=SYNC_CREATE_LIMIT,
	)


def create_missing_variants_job(filters=None, use_template_image=False, ignore_permissions=False, limit=MAX_CREATE_ROWS):
	filters = parse_filters(filters)
	report = VariantCoverageReport(filters)
	missing_rows = report.get_missing_rows(limit=limit)

	created = 0
	skipped = 0
	errors = []

	for row in missing_rows:
		attributes = json.loads(row["combination_json"])
		if get_variant(row["item_template"], attributes):
			skipped += 1
			continue

		try:
			variant = create_variant(row["item_template"], attributes, use_template_image=use_template_image)
			variant.save(ignore_permissions=ignore_permissions)
			created += 1
		except Exception as exc:
			errors.append(
				{
					"item_template": row["item_template"],
					"attributes": row["variant_attributes"],
					"error": cstr(exc),
				}
			)

	if errors:
		frappe.log_error(
			title=_("Variant Coverage Creation Errors"),
			message=frappe.as_json(errors, indent=2),
		)

	return {"created": created, "skipped": skipped, "queued": 0, "errors": len(errors)}


class VariantCoverageReport:
	def __init__(self, filters):
		self.filters = frappe._dict(filters or {})
		self.variant_attribute = self.filters.get("variant_attribute") or DEFAULT_VARIANT_ATTRIBUTE
		self.status = self.filters.get("status") or "All"
		self.include_disabled_variants = cint(self.filters.get("include_disabled_variants"))
		self._attribute_values = None

	def get_rows(self):
		rows = self._build_rows(limit=MAX_PREVIEW_ROWS + 1)
		if len(rows) > MAX_PREVIEW_ROWS:
			frappe.msgprint(
				_("Showing first {0} rows. Please narrow filters to see the full variant coverage.").format(
					MAX_PREVIEW_ROWS
				),
				indicator="orange",
			)
			rows = rows[:MAX_PREVIEW_ROWS]

		return rows

	def get_missing_rows(self, limit=None):
		original_status = self.status
		self.status = "Missing"
		try:
			return self._build_rows(limit=limit)
		finally:
			self.status = original_status

	def _build_rows(self, limit=None):
		rows = []
		for template in self._get_templates():
			attribute_options = self._get_template_attribute_options(template.name)
			if not attribute_options or self.variant_attribute not in attribute_options:
				continue

			combinations = generate_keyed_value_combinations(attribute_options)
			existing_variants = self._get_existing_variant_map(template.name)

			for combination in combinations:
				variant = existing_variants.get(self._combination_key(combination))
				status = "Created" if variant else "Missing"
				if self.status != "All" and self.status != status:
					continue

				row = self._make_row(template, combination, variant, status)
				rows.append(row)

				if limit and len(rows) >= limit:
					return self._sort_rows(rows)

		return self._sort_rows(rows)

	def _get_templates(self):
		filters = {
			"has_variants": 1,
			"variant_based_on": "Item Attribute",
		}
		if self.filters.get("item_template"):
			filters["name"] = self.filters.item_template
		if self.filters.get("item_group"):
			filters["item_group"] = self.filters.item_group

		return frappe.db.get_all(
			"Item",
			fields=["name", "item_name"],
			filters=filters,
			order_by="name",
		)

	def _get_template_attribute_options(self, template):
		rows = frappe.db.get_all(
			"Item Variant Attribute",
			fields=["attribute", "numeric_values", "from_range", "to_range", "increment"],
			filters={"parent": template},
			order_by="idx",
		)

		options = {}
		for row in rows:
			values = self._get_attribute_options(row)
			if row.attribute == self.variant_attribute and self.filters.get("attribute_value"):
				values = [value for value in values if value == self.filters.attribute_value]
			if not values:
				return {}

			options[row.attribute] = values

		return options

	def _get_attribute_options(self, row):
		if cint(row.numeric_values):
			return self._get_numeric_options(row)

		values = self._get_attribute_values().get(row.attribute, [])
		if row.attribute == DEFAULT_VARIANT_ATTRIBUTE:
			values = filter_enabled_brand_values(values)

		return values

	def _get_numeric_options(self, row):
		increment = flt(row.increment)
		if not increment:
			return []

		values = []
		current = Decimal(str(row.from_range))
		end = Decimal(str(row.to_range))
		step = Decimal(str(row.increment))

		while current <= end:
			if current == current.to_integral_value():
				values.append(cstr(int(current)))
			else:
				values.append(cstr(current.normalize()))
			current += step

			if len(values) > MAX_PREVIEW_ROWS:
				break

		return values

	def _get_attribute_values(self):
		if self._attribute_values is None:
			self._attribute_values = {}
			for row in frappe.db.get_all(
				"Item Attribute Value",
				fields=["parent", "attribute_value"],
				order_by="idx",
			):
				self._attribute_values.setdefault(row.parent, []).append(row.attribute_value)

		return self._attribute_values

	def _get_existing_variant_map(self, template):
		filters = {"variant_of": template}
		if not self.include_disabled_variants:
			filters["disabled"] = 0

		variants = frappe.db.get_all(
			"Item",
			fields=["name", "item_name"],
			filters=filters,
			order_by="name",
		)
		if not variants:
			return {}

		variant_by_name = {row.name: row for row in variants}
		attribute_rows = frappe.db.get_all(
			"Item Variant Attribute",
			fields=["parent", "attribute", "attribute_value"],
			filters={"parent": ["in", list(variant_by_name)]},
		)

		attributes_by_variant = {}
		for row in attribute_rows:
			attributes_by_variant.setdefault(row.parent, {})[row.attribute] = row.attribute_value

		variant_map = {}
		for variant, attributes in attributes_by_variant.items():
			variant_map[self._combination_key(attributes)] = variant_by_name[variant]

		return variant_map

	def _make_row(self, template, combination, variant, status):
		return {
			"item_template": template.name,
			"template_item_name": template.item_name,
			"variant_attribute": self.variant_attribute,
			"attribute_value": combination.get(self.variant_attribute),
			"variant_attributes": self._format_attributes(combination),
			"status": status,
			"variant_item": variant.name if variant else None,
			"variant_item_name": variant.item_name if variant else None,
			"combination_json": json.dumps(combination, sort_keys=True),
		}

	def _sort_rows(self, rows):
		view_by = self.filters.get("view_by") or "Template"
		if view_by == "Attribute Value":
			return sorted(
				rows,
				key=lambda row: (
					row.get("attribute_value") or "",
					row.get("item_template") or "",
					row.get("status") or "",
					row.get("variant_attributes") or "",
				),
			)

		return sorted(
			rows,
			key=lambda row: (
				row.get("item_template") or "",
				row.get("attribute_value") or "",
				row.get("status") or "",
				row.get("variant_attributes") or "",
			),
		)

	@staticmethod
	def _combination_key(attributes):
		return tuple(sorted((attribute, cstr(value)) for attribute, value in attributes.items()))

	@staticmethod
	def _format_attributes(attributes):
		return ", ".join(f"{attribute}: {value}" for attribute, value in attributes.items())


def filter_enabled_brand_values(values):
	if not values or not frappe.db.has_column("Brand", "disabled"):
		return values

	disabled_brands = set(
		frappe.get_all("Brand", filters={"name": ["in", values], "disabled": 1}, pluck="name")
	)
	if not disabled_brands:
		return values

	return [value for value in values if value not in disabled_brands]


def get_columns():
	return [
		{
			"fieldname": "item_template",
			"label": _("Item Template"),
			"fieldtype": "Link",
			"options": "Item",
			"width": 180,
		},
		{
			"fieldname": "template_item_name",
			"label": _("Template Item Name"),
			"fieldtype": "Data",
			"width": 180,
		},
		{
			"fieldname": "variant_attribute",
			"label": _("Variant Attribute"),
			"fieldtype": "Data",
			"width": 130,
		},
		{
			"fieldname": "attribute_value",
			"label": _("Attribute Value"),
			"fieldtype": "Data",
			"width": 140,
		},
		{
			"fieldname": "variant_attributes",
			"label": _("Full Attribute Combination"),
			"fieldtype": "Data",
			"width": 260,
		},
		{
			"fieldname": "status",
			"label": _("Status"),
			"fieldtype": "Data",
			"width": 100,
		},
		{
			"fieldname": "variant_item",
			"label": _("Variant Item"),
			"fieldtype": "Link",
			"options": "Item",
			"width": 180,
		},
		{
			"fieldname": "variant_item_name",
			"label": _("Variant Item Name"),
			"fieldtype": "Data",
			"width": 180,
		},
		{
			"fieldname": "combination_json",
			"label": _("Combination JSON"),
			"fieldtype": "Code",
			"hidden": 1,
		},
	]


def parse_filters(filters):
	if isinstance(filters, str):
		filters = frappe.parse_json(filters)

	return frappe._dict(filters or {})
