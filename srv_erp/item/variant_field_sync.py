import frappe
from frappe import _
from frappe.model import no_value_fields, table_fields


def validate_item_group_sync(doc, method=None):
	validate_template_controlled_variant_fields(doc, method)


def sync_template_item_group_to_variants(doc, method=None):
	sync_template_fields_to_variants(doc, method)


def sync_variant_item_groups(template_item, item_group=None):
	return sync_variant_item_fields(template_item)


def sync_all_variant_item_groups() -> int:
	return sync_all_variant_item_fields()


VARIANT_SPECIFIC_FIELDS = {
	"naming_series",
	"item_code",
	"variant_of",
	"variant_based_on",
	"has_variants",
	"opening_stock",
	"valuation_rate",
	"last_purchase_rate",
	"default_bom",
	"default_item_manufacturer",
	"default_manufacturer_part_no",
	"total_projected_qty",
}
VARIANT_ITEM_NAME_FIELD = "item_name"


def validate_template_controlled_variant_fields(doc, method=None):
	if not doc.variant_of:
		return

	template = frappe.get_cached_doc("Item", doc.variant_of)
	controlled_fields = get_template_controlled_variant_fields(doc)
	if not controlled_fields:
		return

	blocked_fields = []
	for fieldname in controlled_fields:
		template_value = get_template_controlled_field_value(fieldname, template, doc)
		if doc.get(fieldname) == template_value:
			continue

		if doc.is_new():
			doc.set(fieldname, template_value)
			continue

		if doc.has_value_changed(fieldname):
			blocked_fields.append(fieldname)
			continue

		doc.set(fieldname, template_value)

	if blocked_fields:
		frappe.throw(
			_(
				"Fields {0} for variant {1} are controlled by template {2}. Change these fields on the template instead."
			).format(
				frappe.bold(", ".join(get_field_labels(blocked_fields))),
				frappe.bold(doc.name),
				frappe.bold(doc.variant_of),
			)
		)


def sync_template_fields_to_variants(doc, method=None):
	if doc.variant_of or not doc.has_variants:
		return

	changed_fields = get_changed_template_controlled_fields(doc)
	if not changed_fields:
		return

	sync_variant_item_fields(doc.name, changed_fields, template=doc)


def sync_variant_item_fields(template_item, fieldnames=None, template=None):
	if template is None:
		template = frappe.get_cached_doc("Item", template_item)

	if fieldnames is None:
		fieldnames = get_template_controlled_variant_fields(template)

	if not fieldnames:
		return 0

	if isinstance(fieldnames, str):
		fieldnames = [fieldnames]

	fieldnames = list(dict.fromkeys(fieldnames))
	sync_item_name = VARIANT_ITEM_NAME_FIELD in fieldnames
	template_fieldnames = [fieldname for fieldname in fieldnames if fieldname != VARIANT_ITEM_NAME_FIELD]

	if template_fieldnames:
		sync_variant_template_fields(template_item, template_fieldnames)

	if sync_item_name:
		sync_variant_item_names(template)

	return 1


def sync_variant_template_fields(template_item, fieldnames):
	template_values = frappe.db.get_value("Item", template_item, fieldnames, as_dict=True)
	if not template_values:
		return

	assignments = []
	values = {"template_item": template_item, "user": frappe.session.user}
	conditions = []
	for fieldname in fieldnames:
		value_key = f"value_{fieldname}"
		if fieldname == "disabled" and frappe.db.has_column("Item", "dynamic_item_approval_status"):
			assignments.append(
				f"`{fieldname}` = case "
				"when `dynamic_item_approval_status` = %(pending_approval)s "
				f"then `{fieldname}` else %({value_key})s end"
			)
			conditions.append(
				"(ifnull(`dynamic_item_approval_status`, '') != %(pending_approval)s "
				f"and ifnull(`{fieldname}`, '') != ifnull(%({value_key})s, ''))"
			)
			values["pending_approval"] = "Pending Approval"
		else:
			assignments.append(f"`{fieldname}` = %({value_key})s")
			conditions.append(f"ifnull(`{fieldname}`, '') != ifnull(%({value_key})s, '')")
		values[value_key] = template_values.get(fieldname)

	if not assignments:
		return 0

	frappe.db.sql(
		f"""
		update `tabItem`
		set {", ".join(assignments)},
			modified = now(),
			modified_by = %(user)s
		where variant_of = %(template_item)s
			and ({ " or ".join(conditions) })
		""",
		values,
	)


def sync_variant_item_names(template):
	for variant_name in frappe.get_all("Item", filters={"variant_of": template.name}, pluck="name"):
		variant = frappe.get_doc("Item", variant_name)
		item_name = get_variant_item_name(template, variant)
		if variant.item_name == item_name:
			continue

		frappe.db.set_value("Item", variant.name, VARIANT_ITEM_NAME_FIELD, item_name)


def get_template_controlled_field_value(fieldname, template, variant):
	if fieldname == "disabled" and variant.get("dynamic_item_approval_status") == "Pending Approval":
		return 1
	if fieldname == "standard_rate" and variant.get("dynamic_item_approval_status") == "Pending Approval":
		return 0
	if fieldname == VARIANT_ITEM_NAME_FIELD:
		return get_variant_item_name(template, variant)

	return template.get(fieldname)


def get_variant_item_name(template, variant):
	parts = [template.item_name or template.item_code or template.name]
	parts.extend(get_variant_attribute_values(variant))
	return " - ".join(part for part in parts if part)


def get_variant_attribute_values(variant):
	return [
		row.attribute_value
		for row in variant.get("attributes") or []
		if row.attribute_value
	]


def sync_all_variant_item_fields() -> int:
	template_names = frappe.get_all(
		"Item",
		filters={"has_variants": 1},
		pluck="name",
	)
	for template_item in template_names:
		sync_variant_item_fields(template_item)

	return len(template_names)


def get_changed_template_controlled_fields(doc):
	controlled_fields = get_template_controlled_variant_fields(doc)
	if doc.is_new():
		return controlled_fields

	previous = doc.get_doc_before_save()
	if not previous:
		return []

	return [fieldname for fieldname in controlled_fields if previous.get(fieldname) != doc.get(fieldname)]


def get_template_controlled_variant_fields(doc=None):
	meta = frappe.get_meta("Item")
	return [
		df.fieldname
		for df in meta.fields
		if is_template_controlled_variant_field(df, doc)
	]


def is_template_controlled_variant_field(df, doc=None):
	if not df.fieldname:
		return False
	if df.fieldname in VARIANT_SPECIFIC_FIELDS:
		return False
	if df.fieldtype in no_value_fields or df.fieldtype in table_fields:
		return False
	if df.read_only or df.no_copy:
		return False
	if doc and is_variant_attribute_field(doc, df.fieldname):
		return False
	if (
		doc
		and df.fieldname == "disabled"
		and doc.get("dynamic_item_approval_status") == "Pending Approval"
	):
		return False

	return True


def is_variant_attribute_field(doc, fieldname):
	if fieldname == "brand":
		return has_variant_attribute(doc, "Brand")

	return False


def has_variant_attribute(doc, attribute):
	for row in doc.get("attributes") or []:
		if row.attribute == attribute:
			return True
	return False


def get_field_labels(fieldnames):
	meta = frappe.get_meta("Item")
	return [meta.get_label(fieldname) or fieldname for fieldname in fieldnames]


def has_item_group_changed(doc) -> bool:
	if doc.is_new():
		return True

	previous = doc.get_doc_before_save()
	if not previous:
		return False

	return previous.item_group != doc.item_group
