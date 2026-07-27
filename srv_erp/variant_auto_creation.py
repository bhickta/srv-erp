import frappe
from frappe.utils import cint

from srv_erp.srv_erp.report.variant_coverage.variant_coverage import (
	DEFAULT_VARIANT_ATTRIBUTE,
	create_missing_variants_job,
)


def handle_item_attribute_update(doc, method=None):
	if not should_sync_for_item_attribute(doc):
		return

	sync_missing_brand_variants(enqueue=True)


def should_sync_for_item_attribute(doc) -> bool:
	if not cint(frappe.db.get_single_value("SRV Settings", "auto_create_variants_on_brand_update")):
		return False

	attribute = get_auto_create_variant_attribute()
	if doc.name != attribute:
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


def sync_missing_brand_variants(enqueue=False):
	attribute = get_auto_create_variant_attribute()
	if not cint(frappe.db.get_single_value("SRV Settings", "auto_create_variants_on_brand_update")):
		return {"created": 0, "skipped": 0, "queued": 0, "disabled": 1}

	if not frappe.db.exists("Item Attribute", attribute):
		return {"created": 0, "skipped": 0, "queued": 0, "missing_attribute": attribute}

	use_template_image = cint(
		frappe.db.get_single_value("SRV Settings", "variant_auto_create_use_template_image")
	)

	if enqueue and not frappe.flags.in_test:
		frappe.enqueue(
			"srv_erp.variant_auto_creation.sync_missing_brand_variants_job",
			queue="long",
			attribute=attribute,
			use_template_image=use_template_image,
		)
		return {"created": 0, "skipped": 0, "queued": 1}

	return sync_missing_brand_variants_job(attribute, use_template_image)


def sync_missing_brand_variants_job(attribute=None, use_template_image=False):
	attribute = attribute or get_auto_create_variant_attribute()
	return create_missing_variants_job(
		filters={"variant_attribute": attribute},
		use_template_image=use_template_image,
		ignore_permissions=True,
		limit=None,
	)


def get_auto_create_variant_attribute() -> str:
	return (
		frappe.db.get_single_value("SRV Settings", "variant_auto_create_attribute")
		or DEFAULT_VARIANT_ATTRIBUTE
	)


def set_srv_settings_defaults():
	if not frappe.db.get_single_value("SRV Settings", "variant_auto_create_attribute"):
		frappe.db.set_single_value(
			"SRV Settings", "variant_auto_create_attribute", DEFAULT_VARIANT_ATTRIBUTE
		)

	if frappe.db.get_single_value("SRV Settings", "auto_create_variants_on_brand_update") is None:
		frappe.db.set_single_value("SRV Settings", "auto_create_variants_on_brand_update", 0)

	if frappe.db.get_single_value("SRV Settings", "variant_auto_create_use_template_image") is None:
		frappe.db.set_single_value("SRV Settings", "variant_auto_create_use_template_image", 0)
