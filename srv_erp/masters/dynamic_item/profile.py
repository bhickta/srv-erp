from __future__ import annotations

import frappe
from erpnext.controllers.item_variant import validate_is_incremental
from frappe import _
from frappe.utils import cint

from srv_erp.item.variant_auto_creation import is_brand_disabled
from srv_erp.masters.dynamic_item.configuration import is_grid_enabled
from srv_erp.masters.dynamic_item.lookups import (
	get_case_insensitive_attribute_value,
	get_case_insensitive_name,
)
from srv_erp.masters.dynamic_item.normalization import normalize_text


def validate_source(source):
	if not source:
		return frappe._dict()
	if not isinstance(source, dict):
		frappe.throw(_("Source must be a JSON object."))
	source = frappe._dict(source)
	if source.doctype or source.fieldname:
		if not source.doctype or not source.fieldname:
			frappe.throw(_("Source DocType and fieldname must be supplied together."))
		if not is_grid_enabled(source.doctype, source.fieldname):
			frappe.throw(
				_("Dynamic Item Requests are not enabled for {0}.{1}.").format(
					frappe.bold(source.doctype), frappe.bold(source.fieldname)
				)
			)
	return source


def get_template_and_profile(template_item: str):
	template_item = normalize_text(template_item, _("Item Template"))
	template = frappe.get_doc("Item", template_item)
	if not template.has_permission("read"):
		frappe.throw(_("Not permitted to read Item template {0}.").format(frappe.bold(template_item)))
	if template.disabled:
		frappe.throw(_("Item template {0} is disabled.").format(frappe.bold(template_item)))
	if not cint(template.has_variants) or template.variant_based_on != "Item Attribute":
		frappe.throw(_("{0} is not an Item Attribute-based template.").format(frappe.bold(template_item)))
	if not frappe.db.exists("Dynamic Variant Profile", template_item):
		frappe.throw(
			_("Dynamic Variant Profile is not configured for {0}.").format(frappe.bold(template_item))
		)
	profile = frappe.get_doc("Dynamic Variant Profile", template_item)
	if not cint(profile.enabled):
		frappe.throw(_("Dynamic Variant Profile is disabled for {0}.").format(frappe.bold(template_item)))
	return template, profile


def get_profile_rules(profile) -> dict[str, frappe._dict]:
	return {row.item_attribute: row for row in profile.get("attributes") or [] if row.item_attribute}


def validate_requested_attributes(template, profile, attributes: dict[str, str]):
	rules = get_profile_rules(profile)
	missing = [
		attribute
		for attribute, rule in rules.items()
		if cint(rule.required_parameter) and not attributes.get(attribute)
	]
	if missing:
		frappe.throw(
			_("Missing required variant attributes: {0}.").format(
				", ".join(frappe.bold(attribute) for attribute in missing)
			)
		)

	template_attributes = {row.attribute for row in template.get("attributes") or []}
	for attribute, value in attributes.items():
		rule = rules.get(attribute)
		attribute_exists = frappe.db.exists("Item Attribute", attribute)
		if not rule:
			frappe.throw(
				_("Attribute {0} is not configured for Item template {1}.").format(
					frappe.bold(attribute), frappe.bold(template.name)
				)
			)
		if attribute.casefold() == "brand":
			brand = get_case_insensitive_name("Brand", value)
			if brand and is_brand_disabled(brand):
				frappe.throw(_("Brand {0} is disabled.").format(frappe.bold(brand)))
		if attribute_exists and cint(frappe.db.get_value("Item Attribute", attribute, "numeric_values")):
			if not rule or attribute not in template_attributes:
				frappe.throw(
					_("Numeric attribute {0} must be configured on the template profile first.").format(
						frappe.bold(attribute)
					)
				)
			validate_numeric_value(template.name, attribute, value)
		elif not attribute_exists or not get_case_insensitive_attribute_value(attribute, value):
			frappe.throw(
				_("Select a predefined value for attribute {0}.").format(frappe.bold(attribute))
			)


def validate_numeric_value(template_item: str, attribute: str, value: str):
	row = frappe.db.get_value(
		"Item Variant Attribute",
		{"parent": template_item, "attribute": attribute},
		["from_range", "to_range", "increment"],
		as_dict=True,
	)
	if not row:
		frappe.throw(_("Numeric attribute {0} is not configured on the template.").format(attribute))
	validate_is_incremental(row, attribute, value, template_item)
