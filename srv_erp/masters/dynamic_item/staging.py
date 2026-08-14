from __future__ import annotations

import frappe
from erpnext.controllers.item_variant import create_variant
from frappe import _
from frappe.utils import cint, cstr

from srv_erp.item.variant_auto_creation import (
	get_brand_abbreviation,
	is_brand_disabled,
	make_attribute_abbr,
)
from srv_erp.masters.dynamic_item.configuration import PENDING, get_settings
from srv_erp.masters.dynamic_item.context import dynamic_item_service_context
from srv_erp.masters.dynamic_item.exceptions import DynamicItemConflict
from srv_erp.masters.dynamic_item.lookups import (
	get_case_insensitive_attribute_value,
	get_case_insensitive_name,
)
from srv_erp.masters.dynamic_item.packaging import add_packaging_rows
from srv_erp.masters.dynamic_item.repository import get_variant_if_present


def stage_requested_schema(request, template, profile) -> dict[str, str]:
	canonical = {}
	profile_changed = False
	template_changed = False
	template_attributes = {row.attribute for row in template.get("attributes") or []}
	profile_attributes = {row.item_attribute for row in profile.get("attributes") or []}

	for row in request.attributes:
		attribute, attribute_created = ensure_item_attribute(row.item_attribute)
		row.item_attribute = attribute
		row.attribute_was_created = cint(attribute_created)
		value, abbreviation, value_created, master_created = ensure_attribute_value(
			attribute, row.attribute_value
		)
		row.attribute_value = value
		row.abbreviation = abbreviation
		row.value_was_created = cint(value_created)
		row.master_was_created = cint(master_created)
		canonical[attribute] = value

		if attribute not in template_attributes:
			item_attribute = frappe.get_doc("Item Attribute", attribute)
			if cint(item_attribute.numeric_values):
				frappe.throw(_("Numeric attributes must be attached to templates by a Masters manager."))
			template.append("attributes", {"attribute": attribute, "numeric_values": 0})
			template_attributes.add(attribute)
			row.template_link_was_created = 1
			template_changed = True

		if attribute not in profile_attributes:
			profile.append(
				"attributes",
				{
					"item_attribute": attribute,
					"required_parameter": 0,
					"allow_new_values": 1,
				},
			)
			profile_attributes.add(attribute)
			row.profile_row_was_created = 1
			profile_changed = True

	if template_changed:
		template.flags.dont_update_variants = True
		with dynamic_item_service_context():
			template.save(ignore_permissions=True)
	if profile_changed:
		with dynamic_item_service_context():
			profile.save(ignore_permissions=True)
	return canonical


def ensure_item_attribute(attribute: str) -> tuple[str, bool]:
	existing = get_case_insensitive_name("Item Attribute", attribute)
	if existing:
		return existing, False
	if not cint(get_settings().allow_dynamic_attributes):
		frappe.throw(_("Item Attribute {0} does not exist.").format(frappe.bold(attribute)))
	with dynamic_item_service_context():
		doc = frappe.get_doc(
			{
				"doctype": "Item Attribute",
				"attribute_name": attribute,
				"numeric_values": 0,
			}
		).insert(ignore_permissions=True)
	return doc.name, True


def ensure_attribute_value(attribute: str, value: str) -> tuple[str, str | None, bool, bool]:
	item_attribute = frappe.get_doc("Item Attribute", attribute)
	if cint(item_attribute.numeric_values):
		return value, None, False, False

	existing = get_case_insensitive_attribute_value(attribute, value)
	if existing:
		abbr = frappe.db.get_value(
			"Item Attribute Value",
			{"parent": attribute, "attribute_value": existing},
			"abbr",
		)
		return existing, abbr, False, False

	master_created = False
	if attribute.casefold() == "brand":
		brand = get_case_insensitive_name("Brand", value)
		if brand and is_brand_disabled(brand):
			frappe.throw(_("Brand {0} is disabled.").format(frappe.bold(brand)))
		if not brand:
			existing_abbrs = {
				cstr(row.abbr).casefold()
				for row in item_attribute.get("item_attribute_values") or []
				if row.abbr
			}
			abbr = make_attribute_abbr(value, existing_abbrs)
			brand_doc = {"doctype": "Brand", "brand": value}
			if frappe.db.has_column("Brand", "brand_abbreviation"):
				brand_doc["brand_abbreviation"] = abbr
			with dynamic_item_service_context():
				frappe.get_doc(brand_doc).insert(ignore_permissions=True)
			master_created = True
			brand = value
		value = brand

	existing_abbrs = {
		cstr(row.abbr).casefold() for row in item_attribute.get("item_attribute_values") or [] if row.abbr
	}
	abbr = get_brand_abbreviation(value) if attribute.casefold() == "brand" else None
	if not abbr or abbr.casefold() in existing_abbrs:
		abbr = make_attribute_abbr(value, existing_abbrs)
	item_attribute.append("item_attribute_values", {"attribute_value": value, "abbr": abbr})
	with dynamic_item_service_context():
		item_attribute.save(ignore_permissions=True)
	return value, abbr, True, master_created


def stage_variant_item(request, template, attributes: dict[str, str], identity_signature: str):
	existing = get_variant_if_present(template.name, attributes)
	if existing:
		frappe.throw(
			_("Matching Item {0} was created concurrently. Retry the request.").format(frappe.bold(existing)),
			DynamicItemConflict,
		)

	variant = create_variant(
		template.name,
		attributes,
		use_template_image=cint(get_settings().use_template_image),
	)
	if not variant.item_code:
		frappe.throw(_("ERPNext could not generate an Item Code for the requested attributes."))
	if frappe.db.exists("Item", variant.item_code):
		frappe.throw(
			_(
				"Generated Item Code {0} conflicts with a different Item. Review attribute abbreviations."
			).format(frappe.bold(variant.item_code)),
			DynamicItemConflict,
		)

	variant.disabled = 1
	variant.opening_stock = 0
	variant.standard_rate = 0
	variant.dynamic_item_approval_status = PENDING
	variant.dynamic_item_request = request.name
	variant.dynamic_variant_signature = identity_signature
	variant.dynamic_item_requested_by = request.requested_by
	add_packaging_rows(variant, [row.as_dict() for row in request.uoms])

	with dynamic_item_service_context():
		variant.insert(ignore_permissions=True)
	request.staged_item_code = variant.name
