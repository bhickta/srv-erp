import re

import frappe
from frappe import _
from frappe.utils import cint

from srv_erp.srv_erp.report.variant_coverage.variant_coverage import (
	DEFAULT_VARIANT_ATTRIBUTE,
	MAX_CREATE_ROWS,
	SYNC_CREATE_LIMIT,
	VariantCoverageReport,
	create_missing_variants,
	create_missing_variants_job,
)


def handle_item_attribute_update(doc, method=None):
	if not should_sync_for_item_attribute(doc):
		return

	sync_missing_brand_variants(enqueue=True)


def handle_brand_update(doc, method=None):
	if frappe.flags.syncing_brand_master_values:
		return

	if is_brand_disabled(doc.get("brand") or doc.name):
		remove_brand_attribute_value(doc.get("brand") or doc.name)
		return

	brand = doc.get("brand") or doc.name
	ensure_brand_attribute_value(brand)
	sync_missing_brand_variants(enqueue=True, attribute_value=brand)


def handle_brand_delete(doc, method=None):
	remove_brand_attribute_value(doc.get("brand") or doc.name)


def validate_brand_abbreviation(doc, method=None):
	abbr = doc.get("brand_abbreviation")
	if not abbr:
		return
	if not has_brand_abbreviation_field():
		return

	existing_brand = frappe.db.get_value(
		"Brand",
		{"brand_abbreviation": abbr, "name": ["!=", doc.name]},
		"name",
	)
	if existing_brand:
		frappe.throw(
			_("Brand Abbreviation {0} is already used by Brand {1}.").format(
				frappe.bold(abbr),
				frappe.bold(existing_brand),
			)
		)


def validate_item_attribute_brand_source(doc, method=None):
	if not is_auto_create_variant_attribute(doc.name):
		return

	if frappe.flags.syncing_brand_attribute_values or getattr(frappe.flags, "dynamic_item_service", False):
		return

	if item_attribute_values_changed(doc):
		frappe.throw(
			_(
				"Brand attribute values are synced from Brand master. Please add or update brands from Brand instead."
			)
		)


def should_sync_for_item_attribute(doc) -> bool:
	if frappe.flags.syncing_brand_attribute_values:
		return False

	if not is_auto_create_variants_enabled():
		return False

	if not is_auto_create_variant_attribute(doc.name):
		return False

	if cint(doc.get("numeric_values")):
		return False

	return item_attribute_values_changed(doc)


def item_attribute_values_changed(doc) -> bool:
	previous = doc.get_doc_before_save()
	if not previous:
		return True

	old_values = {row.attribute_value for row in previous.get("item_attribute_values") if row.attribute_value}
	new_values = {row.attribute_value for row in doc.get("item_attribute_values") if row.attribute_value}
	return old_values != new_values


def ensure_brand_attribute_value(brand):
	attribute = get_auto_create_variant_attribute()
	if not brand or not attribute:
		return {"created": 0, "attribute": attribute}
	if is_brand_disabled(brand):
		return {"created": 0, "attribute": attribute, "disabled": 1}

	brand_abbr = get_brand_abbreviation(brand)
	if not frappe.db.exists("Item Attribute", attribute):
		frappe.flags.syncing_brand_attribute_values = True
		try:
			frappe.get_doc(
				{
					"doctype": "Item Attribute",
					"attribute_name": attribute,
					"item_attribute_values": [
						{"attribute_value": brand, "abbr": brand_abbr or make_attribute_abbr(brand)}
					],
				}
			).insert(ignore_permissions=True)
		finally:
			frappe.flags.syncing_brand_attribute_values = False
		return {"created": 1, "attribute": attribute}

	doc = frappe.get_doc("Item Attribute", attribute)
	if cint(doc.numeric_values):
		return {"created": 0, "attribute": attribute, "numeric": 1}

	existing_row = get_attribute_value_row(doc, brand)
	if existing_row:
		return sync_existing_brand_attribute_value(doc, existing_row, brand_abbr)

	existing_abbrs = get_existing_attribute_abbrs(doc)
	abbr = brand_abbr or make_attribute_abbr(brand, existing_abbrs)
	if brand_abbr and brand_abbr.lower() in existing_abbrs:
		abbr = make_attribute_abbr(brand, existing_abbrs)

	doc.append("item_attribute_values", {"attribute_value": brand, "abbr": abbr})
	save_synced_brand_attribute(doc)
	return {
		"created": 1,
		"attribute": attribute,
		"conflict": cint(bool(brand_abbr and brand_abbr != abbr)),
	}


def sync_existing_brand_attribute_value(doc, row, brand_abbr):
	if not brand_abbr or row.abbr == brand_abbr:
		return {"created": 0, "attribute": doc.name}

	existing_abbrs = get_existing_attribute_abbrs(doc, exclude_row=row)
	if brand_abbr.lower() in existing_abbrs:
		return {
			"created": 0,
			"updated": 0,
			"conflict": 1,
			"attribute": doc.name,
			"kept_abbr": row.abbr,
			"skipped_abbr": brand_abbr,
		}

	row.abbr = brand_abbr
	save_synced_brand_attribute(doc)
	return {"created": 0, "updated": 1, "attribute": doc.name}


def save_synced_brand_attribute(doc):
	frappe.flags.syncing_brand_attribute_values = True
	try:
		doc.save(ignore_permissions=True)
	finally:
		frappe.flags.syncing_brand_attribute_values = False


def get_brand_abbreviation(brand):
	if not has_brand_abbreviation_field():
		return None

	return frappe.db.get_value("Brand", brand, "brand_abbreviation")


def has_brand_abbreviation_field():
	return frappe.db.has_column("Brand", "brand_abbreviation")


def get_attribute_value_row(doc, attribute_value):
	for row in doc.item_attribute_values:
		if row.attribute_value == attribute_value:
			return row
	return None


def get_existing_attribute_abbrs(doc, exclude_row=None):
	return {row.abbr.lower() for row in doc.item_attribute_values if row.abbr and row != exclude_row}


def sync_brand_abbreviation_from_attribute(brand, abbr):
	if not brand or not abbr:
		return 0
	if not has_brand_abbreviation_field():
		return 0
	if frappe.db.get_value("Brand", brand, "brand_abbreviation"):
		return 0

	frappe.db.set_value(
		"Brand",
		brand,
		"brand_abbreviation",
		abbr,
		update_modified=False,
	)
	return 1


def is_brand_disabled(brand):
	if not has_brand_disabled_field():
		return False

	return cint(frappe.db.get_value("Brand", brand, "disabled"))


def has_brand_disabled_field():
	return frappe.db.has_column("Brand", "disabled")


def disable_brand_variants(brand):
	if not brand:
		return {"disabled": 0}

	attribute = get_auto_create_variant_attribute()
	variant_names = frappe.db.sql_list(
		"""
		select distinct item.name
		from `tabItem` item
		inner join `tabItem Variant Attribute` attribute
			on attribute.parent = item.name
		where item.variant_of is not null
			and item.variant_of != ''
			and item.disabled = 0
			and attribute.attribute = %(attribute)s
			and attribute.attribute_value = %(brand)s
		""",
		{"attribute": attribute, "brand": brand},
	)

	for item in variant_names:
		frappe.db.set_value("Item", item, "disabled", 1)

	return {"disabled": len(variant_names)}


def remove_brand_attribute_value(brand):
	if not brand:
		return {"removed": 0, "disabled": 0}

	attribute = get_auto_create_variant_attribute()
	disabled_result = disable_brand_variants(brand)
	if not frappe.db.exists("Item Attribute", attribute):
		return {"removed": 0, "disabled": disabled_result.get("disabled", 0)}

	doc = frappe.get_doc("Item Attribute", attribute)
	original_count = len(doc.item_attribute_values)
	doc.set(
		"item_attribute_values",
		[row for row in doc.item_attribute_values if row.attribute_value != brand],
	)
	removed = original_count - len(doc.item_attribute_values)
	if removed:
		save_synced_brand_attribute(doc)

	return {"removed": removed, "disabled": disabled_result.get("disabled", 0)}


def sync_brand_master_values_to_attribute():
	created = 0
	updated = 0
	disabled = 0
	removed = 0
	conflicts = []
	enabled_brands = []
	for brand in frappe.get_all("Brand", pluck="name"):
		result = ensure_brand_attribute_value(brand)
		created += cint(result.get("created"))
		updated += cint(result.get("updated"))
		disabled += cint(result.get("disabled"))
		if result.get("disabled"):
			removed += remove_brand_attribute_value(brand).get("removed", 0)
		else:
			enabled_brands.append(brand)
		if result.get("conflict"):
			conflicts.append(
				{
					"brand": brand,
					"kept_abbr": result.get("kept_abbr"),
					"skipped_abbr": result.get("skipped_abbr"),
				}
			)

	if conflicts:
		frappe.log_error(
			title=_("Brand Abbreviation Sync Conflicts"),
			message=frappe.as_json(conflicts, indent=2),
		)

	removed += remove_stale_brand_attribute_values(set(enabled_brands))

	return {
		"created": created,
		"updated": updated,
		"disabled": disabled,
		"removed": removed,
		"conflicts": len(conflicts),
	}


def remove_stale_brand_attribute_values(enabled_brands):
	attribute = get_auto_create_variant_attribute()
	if not frappe.db.exists("Item Attribute", attribute):
		return 0

	doc = frappe.get_doc("Item Attribute", attribute)
	stale_values = [
		row.attribute_value
		for row in doc.item_attribute_values
		if row.attribute_value and row.attribute_value not in enabled_brands
	]
	if not stale_values:
		return 0

	for brand in stale_values:
		disable_brand_variants(brand)

	doc.set(
		"item_attribute_values",
		[row for row in doc.item_attribute_values if row.attribute_value not in stale_values],
	)
	save_synced_brand_attribute(doc)
	return len(stale_values)


def sync_attribute_brand_values_to_master():
	attribute = get_auto_create_variant_attribute()
	if not frappe.db.exists("Item Attribute", attribute):
		return {"created": 0, "attribute": attribute, "missing_attribute": 1}

	created = 0
	updated = 0
	for row in frappe.get_all(
		"Item Attribute Value",
		fields=["attribute_value", "abbr"],
		filters={"parent": attribute},
		order_by="idx",
	):
		brand = row.attribute_value
		if not brand:
			continue

		if frappe.db.exists("Brand", brand):
			updated += sync_brand_abbreviation_from_attribute(brand, row.abbr)
			continue

		frappe.flags.syncing_brand_master_values = True
		try:
			brand_doc = frappe.get_doc({"doctype": "Brand", "brand": brand})
			if has_brand_abbreviation_field():
				brand_doc.brand_abbreviation = row.abbr
			brand_doc.insert(ignore_permissions=True)
		finally:
			frappe.flags.syncing_brand_master_values = False
		created += 1

	return {"created": created, "updated": updated, "attribute": attribute}


def make_attribute_abbr(value, existing_abbrs=None):
	existing_abbrs = existing_abbrs or set()
	existing_abbrs = {abbr.lower() for abbr in existing_abbrs}
	words = re.findall(r"[A-Za-z0-9]+", value or "")
	base = "".join(word[0] for word in words).upper()
	if not base:
		base = re.sub(r"[^A-Za-z0-9]", "", value or "").upper()
	base = (base or "BR")[:8]

	abbr = base
	counter = 2
	while abbr.lower() in existing_abbrs:
		suffix = str(counter)
		abbr = f"{base[: 8 - len(suffix)]}{suffix}"
		counter += 1

	return abbr


def sync_missing_brand_variants(enqueue=False, attribute_value=None, limit=None):
	attribute = get_auto_create_variant_attribute()
	if not is_auto_create_variants_enabled():
		return {"created": 0, "skipped": 0, "queued": 0, "disabled": 1}

	if not frappe.db.exists("Item Attribute", attribute):
		return {"created": 0, "skipped": 0, "queued": 0, "missing_attribute": attribute}

	use_template_image = cint(
		frappe.db.get_single_value("SRV Settings", "variant_auto_create_use_template_image")
	)
	filters = {"variant_attribute": attribute}
	if attribute_value:
		filters["attribute_value"] = attribute_value

	if enqueue and attribute_value:
		job_id = get_brand_variant_sync_job_id(attribute, attribute_value)
		frappe.enqueue(
			"srv_erp.item.variant_auto_creation.sync_missing_brand_variants_job",
			queue="long",
			timeout=1500,
			enqueue_after_commit=True,
			deduplicate=True,
			job_id=job_id,
			attribute=attribute,
			use_template_image=use_template_image,
			attribute_value=attribute_value,
			limit=limit,
		)
		return {"created": 0, "skipped": 0, "queued": 1, "job_id": job_id}

	create_limit = limit or SYNC_CREATE_LIMIT
	missing_rows = VariantCoverageReport(filters).get_missing_rows(limit=create_limit + 1)

	if not missing_rows:
		return {"created": 0, "skipped": 0, "queued": 0}

	if len(missing_rows) > create_limit:
		return {
			"created": 0,
			"skipped": 0,
			"queued": 0,
			"too_many": len(missing_rows),
			"limit": create_limit,
		}

	result = sync_missing_brand_variants_job(
		attribute,
		use_template_image,
		attribute_value=attribute_value,
		limit=create_limit,
	)
	result["limit"] = create_limit
	return result


def get_brand_variant_sync_job_id(attribute, attribute_value):
	return f"srv_erp:brand_variant_sync:{attribute}:{attribute_value}"


def sync_missing_brand_variants_job(
	attribute=None,
	use_template_image=False,
	attribute_value=None,
	limit=SYNC_CREATE_LIMIT,
):
	if not is_auto_create_variants_enabled():
		return {"created": 0, "skipped": 0, "queued": 0, "disabled": 1}
	attribute = attribute or get_auto_create_variant_attribute()
	filters = {"variant_attribute": attribute}
	if attribute_value:
		filters["attribute_value"] = attribute_value

	return create_missing_variants_job(
		filters=filters,
		use_template_image=use_template_image,
		ignore_permissions=True,
		limit=limit,
	)


@frappe.whitelist()
def get_item_attribute_variant_sync_status(attribute):
	if not is_auto_create_variant_attribute(attribute):
		return {"applicable": 0}

	missing_rows = VariantCoverageReport({"variant_attribute": attribute}).get_missing_rows(
		limit=MAX_CREATE_ROWS + 1
	)

	return {
		"applicable": 1,
		"attribute": attribute,
		"auto_create_enabled": cint(is_auto_create_variants_enabled()),
		"missing_count": min(len(missing_rows), MAX_CREATE_ROWS),
		"has_more": len(missing_rows) > MAX_CREATE_ROWS,
		"max_create_rows": MAX_CREATE_ROWS,
	}


@frappe.whitelist()
def sync_item_attribute_and_get_status(attribute):
	if not is_auto_create_variant_attribute(attribute):
		return {"applicable": 0}

	if is_auto_create_variants_enabled():
		sync_result = sync_missing_brand_variants(enqueue=True)
		return {
			"applicable": 1,
			"attribute": attribute,
			"auto_create_enabled": 1,
			"created": sync_result.get("created", 0),
			"queued": sync_result.get("queued", 0),
			"skipped": sync_result.get("skipped", 0),
			"errors": sync_result.get("errors", 0),
			"too_many": sync_result.get("too_many", 0),
			"limit": sync_result.get("limit", SYNC_CREATE_LIMIT),
			"has_more": sync_result.get("has_more", 0),
		}

	return get_item_attribute_variant_sync_status(attribute)


@frappe.whitelist()
def create_missing_variants_for_item_attribute(attribute, use_template_image=None):
	if not is_auto_create_variant_attribute(attribute):
		frappe.throw(
			_("Variant auto creation is configured for {0}.").format(get_auto_create_variant_attribute())
		)

	if use_template_image is None:
		use_template_image = frappe.db.get_single_value(
			"SRV Settings", "variant_auto_create_use_template_image"
		)

	return create_missing_variants(
		filters={"variant_attribute": attribute},
		use_template_image=cint(use_template_image),
	)


@frappe.whitelist()
def sync_brand_attribute_and_get_status(brand):
	result = ensure_brand_attribute_value(brand)
	if is_auto_create_variants_enabled():
		sync_result = sync_missing_brand_variants(enqueue=True, attribute_value=brand)
		return {
			"applicable": 1,
			"attribute": result.get("attribute"),
			"brand": brand,
			"auto_create_enabled": 1,
			"attribute_value_created": result.get("created", 0),
			"created": sync_result.get("created", 0),
			"queued": sync_result.get("queued", 0),
			"skipped": sync_result.get("skipped", 0),
			"errors": sync_result.get("errors", 0),
			"too_many": sync_result.get("too_many", 0),
			"limit": sync_result.get("limit", SYNC_CREATE_LIMIT),
			"has_more": sync_result.get("has_more", 0),
		}

	status = get_item_attribute_variant_sync_status(result.get("attribute"))
	status["attribute_value_created"] = result.get("created", 0)
	return status


@frappe.whitelist()
def sync_brand_masters_and_get_status():
	result = sync_brand_master_values_to_attribute()
	attribute = get_auto_create_variant_attribute()
	attribute_values_created = cint(result.get("created"))

	if is_auto_create_variants_enabled():
		sync_result = sync_missing_brand_variants(enqueue=True)
		return {
			"applicable": 1,
			"attribute": attribute,
			"auto_create_enabled": 1,
			"attribute_value_created": attribute_values_created,
			"attribute_value_removed": result.get("removed", 0),
			"created": sync_result.get("created", 0),
			"queued": sync_result.get("queued", 0),
			"skipped": sync_result.get("skipped", 0),
			"errors": sync_result.get("errors", 0),
			"too_many": sync_result.get("too_many", 0),
			"limit": sync_result.get("limit", SYNC_CREATE_LIMIT),
		}

	status = get_item_attribute_variant_sync_status(attribute)
	status["attribute_value_created"] = attribute_values_created
	status["attribute_value_removed"] = result.get("removed", 0)
	return status


def get_auto_create_variant_attribute() -> str:
	return (
		frappe.db.get_single_value("SRV Settings", "variant_auto_create_attribute")
		or DEFAULT_VARIANT_ATTRIBUTE
	)


def is_auto_create_variant_attribute(attribute) -> bool:
	return attribute == get_auto_create_variant_attribute()


def is_auto_create_variants_enabled() -> bool:
	from srv_erp.masters.dynamic_item.configuration import (
		is_approval_enforced,
		is_bulk_variant_creation_enabled,
	)

	return bool(
		cint(frappe.db.get_single_value("SRV Settings", "auto_create_variants_on_brand_update"))
		and is_bulk_variant_creation_enabled()
		and not is_approval_enforced()
	)


def set_srv_settings_defaults():
	if not frappe.db.get_single_value("SRV Settings", "variant_auto_create_attribute"):
		frappe.db.set_single_value("SRV Settings", "variant_auto_create_attribute", DEFAULT_VARIANT_ATTRIBUTE)

	if frappe.db.get_single_value("SRV Settings", "auto_create_variants_on_brand_update") is None:
		frappe.db.set_single_value("SRV Settings", "auto_create_variants_on_brand_update", 0)

	if frappe.db.get_single_value("SRV Settings", "variant_auto_create_use_template_image") is None:
		frappe.db.set_single_value("SRV Settings", "variant_auto_create_use_template_image", 0)
