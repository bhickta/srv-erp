import re

import frappe
from frappe import _
from frappe.utils import cint

from srv_erp.srv_erp.report.variant_coverage.variant_coverage import (
	DEFAULT_VARIANT_ATTRIBUTE,
	MAX_CREATE_ROWS,
	VariantCoverageReport,
	create_missing_variants,
	create_missing_variants_job,
)


def handle_item_attribute_update(doc, method=None):
	if not should_sync_for_item_attribute(doc):
		return

	sync_missing_brand_variants(enqueue=True)


def handle_brand_update(doc, method=None):
	ensure_brand_attribute_value(doc.get("brand") or doc.name)


def should_sync_for_item_attribute(doc) -> bool:
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

	if not frappe.db.exists("Item Attribute", attribute):
		frappe.get_doc(
			{
				"doctype": "Item Attribute",
				"attribute_name": attribute,
				"item_attribute_values": [
					{"attribute_value": brand, "abbr": make_attribute_abbr(brand)}
				],
			}
		).insert(ignore_permissions=True)
		return {"created": 1, "attribute": attribute}

	doc = frappe.get_doc("Item Attribute", attribute)
	if cint(doc.numeric_values):
		return {"created": 0, "attribute": attribute, "numeric": 1}

	existing_values = {row.attribute_value for row in doc.item_attribute_values}
	if brand in existing_values:
		return {"created": 0, "attribute": attribute}

	existing_abbrs = {row.abbr for row in doc.item_attribute_values if row.abbr}
	doc.append(
		"item_attribute_values",
		{"attribute_value": brand, "abbr": make_attribute_abbr(brand, existing_abbrs)},
	)
	doc.save(ignore_permissions=True)
	return {"created": 1, "attribute": attribute}


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


def sync_missing_brand_variants(enqueue=False):
	attribute = get_auto_create_variant_attribute()
	if not is_auto_create_variants_enabled():
		return {"created": 0, "skipped": 0, "queued": 0, "disabled": 1}

	if not frappe.db.exists("Item Attribute", attribute):
		return {"created": 0, "skipped": 0, "queued": 0, "missing_attribute": attribute}

	use_template_image = cint(
		frappe.db.get_single_value("SRV Settings", "variant_auto_create_use_template_image")
	)
	missing_rows = VariantCoverageReport({"variant_attribute": attribute}).get_missing_rows(
		limit=MAX_CREATE_ROWS + 1
	)

	if not missing_rows:
		return {"created": 0, "skipped": 0, "queued": 0}

	if enqueue and not frappe.flags.in_test and len(missing_rows) > MAX_CREATE_ROWS:
		frappe.enqueue(
			"srv_erp.variant_auto_creation.sync_missing_brand_variants_job",
			queue="long",
			attribute=attribute,
			use_template_image=use_template_image,
		)
		return {"created": 0, "skipped": 0, "queued": len(missing_rows)}

	return sync_missing_brand_variants_job(attribute, use_template_image)


def sync_missing_brand_variants_job(attribute=None, use_template_image=False):
	attribute = attribute or get_auto_create_variant_attribute()
	return create_missing_variants_job(
		filters={"variant_attribute": attribute},
		use_template_image=use_template_image,
		ignore_permissions=True,
		limit=None,
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
def create_missing_variants_for_item_attribute(attribute, use_template_image=None):
	if not is_auto_create_variant_attribute(attribute):
		frappe.throw(_("Variant auto creation is configured for {0}.").format(get_auto_create_variant_attribute()))

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
	status = get_item_attribute_variant_sync_status(result.get("attribute"))
	status["attribute_value_created"] = result.get("created", 0)
	return status


def get_auto_create_variant_attribute() -> str:
	return (
		frappe.db.get_single_value("SRV Settings", "variant_auto_create_attribute")
		or DEFAULT_VARIANT_ATTRIBUTE
	)


def is_auto_create_variant_attribute(attribute) -> bool:
	return attribute == get_auto_create_variant_attribute()


def is_auto_create_variants_enabled() -> bool:
	return cint(frappe.db.get_single_value("SRV Settings", "auto_create_variants_on_brand_update"))


def set_srv_settings_defaults():
	if not frappe.db.get_single_value("SRV Settings", "variant_auto_create_attribute"):
		frappe.db.set_single_value(
			"SRV Settings", "variant_auto_create_attribute", DEFAULT_VARIANT_ATTRIBUTE
		)

	if frappe.db.get_single_value("SRV Settings", "auto_create_variants_on_brand_update") is None:
		frappe.db.set_single_value("SRV Settings", "auto_create_variants_on_brand_update", 0)

	if frappe.db.get_single_value("SRV Settings", "variant_auto_create_use_template_image") is None:
		frappe.db.set_single_value("SRV Settings", "variant_auto_create_use_template_image", 0)
