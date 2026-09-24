from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint

from srv_erp.item.variant_auto_creation import is_brand_disabled
from srv_erp.masters.dynamic_item.approval_flow import (
	approve_request,
	cancel_request,
	get_request_status,
	reject_request,
)
from srv_erp.masters.dynamic_item.brand_rule_resolution import resolve_effective_rules
from srv_erp.masters.dynamic_item.brand_rules import (
	get_brand_profile,
	resolve_item_group_defaults,
)
from srv_erp.masters.dynamic_item.configuration import (
	get_settings,
	is_bulk_variant_creation_enabled,
	is_dynamic_item_enabled,
	require_requester,
	user_has_approver_role,
	user_has_requester_role,
)
from srv_erp.masters.dynamic_item.lookups import canonicalize_known_masters, get_case_insensitive_name
from srv_erp.masters.dynamic_item.normalization import normalize_attributes, normalize_uoms
from srv_erp.masters.dynamic_item.profile import get_template_and_profile, validate_requested_attributes
from srv_erp.masters.dynamic_item.request_flow import resolve_or_request


@frappe.whitelist()
def get_dynamic_variant_options(
	template_item: str, source_doctype=None, source_field=None, selected_brand=None
) -> dict:
	require_requester()
	if source_doctype or source_field:
		from srv_erp.masters.dynamic_item.profile import validate_source

		validate_source({"doctype": source_doctype, "fieldname": source_field})
	template, profile = get_template_and_profile(template_item)
	return build_variant_options(template, profile, resolve_selected_brand(selected_brand))


def resolve_selected_brand(selected_brand):
	if not selected_brand:
		return None
	canonical = get_case_insensitive_name("Brand", selected_brand)
	if not canonical:
		frappe.throw(_("Select an existing Brand."))
	if is_brand_disabled(canonical):
		frappe.throw(_("Brand {0} is disabled.").format(frappe.bold(canonical)))
	return canonical


def build_variant_options(template, profile, selected_brand=None) -> dict:
	resolved = resolve_effective_rules(template, profile, selected_brand)
	rules = resolved["configuration"].get("attributes", [])
	attributes = []
	template_rows = _template_attribute_rows(template)
	for rule in rules:
		attribute = rule.get("attribute")
		option = _attribute_option(attribute, template_rows.get(attribute))
		option["required"] = bool(rule.get("required"))
		configured_values = rule.get("values") or []
		if configured_values:
			option["values"] = configured_values
		attributes.append(option)
	default_ignored = apply_item_group_defaults(template, selected_brand, attributes, template_rows)
	return {
		"template_item": template.name,
		"stock_uom": template.stock_uom,
		"attributes": attributes,
		"allow_dynamic_attributes": False,
		"uoms": frappe.get_all("UOM", pluck="name", order_by="name"),
		"configuration_source": resolved["source"],
		"configuration_revision": resolved["revision"],
		"requires_brand_selection": resolved["requires_brand_selection"],
		"configuration_fallback": resolved["fallback"],
		"default_ignored": default_ignored,
	}


def _template_attribute_rows(template) -> dict:
	return {
		row.attribute: row
		for row in template.get("attributes") or []
		if not row.disabled and row.attribute
	}


def _attribute_option(attribute: str, row=None) -> dict:
	item_attribute = frappe.get_doc("Item Attribute", attribute)
	numeric = bool(item_attribute.numeric_values)
	return {
		"attribute": attribute,
		"required": False,
		"allow_new_values": False,
		"numeric_values": numeric,
		"values": []
		if numeric
		else [d.attribute_value for d in item_attribute.item_attribute_values],
		"from_range": row.from_range if row else None,
		"to_range": row.to_range if row else None,
		"increment": row.increment if row else None,
	}


def apply_item_group_defaults(template, selected_brand, attributes: list[dict], template_rows=None) -> list[dict]:
	if not selected_brand or not template.item_group:
		return []
	profile = get_brand_profile(selected_brand)
	if not profile:
		return []
	defaults = resolve_item_group_defaults(profile, template.item_group)
	if not defaults:
		return []

	if template_rows is None:
		template_rows = _template_attribute_rows(template)
	by_name = {attribute["attribute"]: attribute for attribute in attributes}
	ignored = []
	for name, value in defaults.items():
		row = template_rows.get(name)
		if not row:
			ignored.append(
				{"attribute": name, "value": value, "reason": _("Attribute is not on this template.")}
			)
			continue
		option = by_name.get(name)
		if not option:
			option = _attribute_option(name, row)
			attributes.append(option)
			by_name[name] = option
		reason = invalid_default_reason(option, value)
		if reason:
			ignored.append({"attribute": name, "value": value, "reason": reason})
			continue
		option["default"] = value
	return ignored


def invalid_default_reason(attribute: dict, value: str) -> str | None:
	if attribute.get("numeric_values"):
		try:
			number = float(value)
		except (TypeError, ValueError):
			return _("Default {0} is not numeric.").format(value)
		from_range = attribute.get("from_range")
		to_range = attribute.get("to_range")
		if from_range is not None and number < float(from_range):
			return _("Default {0} is below the allowed range.").format(value)
		if to_range is not None and number > float(to_range):
			return _("Default {0} is above the allowed range.").format(value)
		return None
	values = attribute.get("values") or []
	if not values:
		return None
	if value.strip().casefold() not in {configured.casefold() for configured in values}:
		return _("Default {0} is not an allowed value.").format(value)
	return None


@frappe.whitelist()
def preview_dynamic_item_variant(payload) -> dict:
	require_requester()
	payload = frappe._dict(frappe.parse_json(payload) if isinstance(payload, str) else payload or {})
	attributes = canonicalize_known_masters(normalize_attributes(payload.get("attributes")))
	uoms = normalize_uoms(payload.get("uoms"))
	template, profile = get_template_and_profile(payload.get("template_item"))
	validate_requested_attributes(template, profile, attributes)
	from erpnext.controllers.item_variant import get_variant

	existing = get_variant(template.name, attributes)
	return {
		"template_item": template.name,
		"attributes": attributes,
		"uoms": uoms,
		"existing_item": existing,
		"requires_approval": not bool(existing) or bool(uoms),
	}


@frappe.whitelist()
def resolve_or_request_item_variant(payload) -> dict:
	return resolve_or_request(payload)


@frappe.whitelist()
def get_dynamic_item_request_status(request: str) -> dict:
	return get_request_status(request)


@frappe.whitelist()
def approve_dynamic_item_request(request: str) -> dict:
	return approve_request(request)


@frappe.whitelist()
def reject_dynamic_item_request(request: str, reason: str) -> dict:
	return reject_request(request, reason)


@frappe.whitelist()
def cancel_dynamic_item_request(request: str, reason=None) -> dict:
	return cancel_request(request, reason)


@frappe.whitelist()
def get_dynamic_item_client_settings(document_type=None) -> dict:
	settings = get_settings()
	feature_enabled = is_dynamic_item_enabled()
	can_request = user_has_requester_role()
	base = {
		"enabled": False,
		"feature_enabled": feature_enabled,
		"can_request": can_request,
		"bulk_variant_creation_enabled": is_bulk_variant_creation_enabled(),
		"approval_enforced": bool(cint(settings.enforce_variant_approval)),
		"grids": [],
	}
	if not feature_enabled or not can_request:
		return base
	grids = [
		{"fieldname": row.table_field, "child_doctype": row.child_doctype}
		for row in settings.get("item_grids") or []
		if cint(row.enabled) and (not document_type or row.document_type == document_type)
	]
	return {
		**base,
		"enabled": True,
		"grids": grids,
		"brand_variant_rules_enabled": bool(cint(settings.get("enable_brand_variant_rules"))),
	}


@frappe.whitelist()
def refresh_masters_configuration() -> dict:
	if "System Manager" not in frappe.get_roles() and not user_has_approver_role():
		frappe.throw(_("Not permitted to refresh Masters configuration."), frappe.PermissionError)
	from srv_erp.masters.setup import bootstrap_dynamic_variant_profiles, sync_dynamic_item_grids

	return {
		"profiles_created": bootstrap_dynamic_variant_profiles(),
		"grids_added": sync_dynamic_item_grids(),
	}
