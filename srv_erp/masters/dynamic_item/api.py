from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint

from srv_erp.masters.dynamic_item.approval_flow import (
	approve_request,
	cancel_request,
	get_request_status,
	reject_request,
)
from srv_erp.masters.dynamic_item.configuration import (
	get_settings,
	is_bulk_variant_creation_enabled,
	is_dynamic_item_enabled,
	require_requester,
	user_has_approver_role,
	user_has_requester_role,
)
from srv_erp.masters.dynamic_item.lookups import canonicalize_known_masters
from srv_erp.masters.dynamic_item.normalization import normalize_attributes, normalize_uoms
from srv_erp.masters.dynamic_item.profile import (
	get_profile_rules,
	get_template_and_profile,
	validate_requested_attributes,
)
from srv_erp.masters.dynamic_item.request_flow import resolve_or_request


@frappe.whitelist()
def get_dynamic_variant_options(template_item: str, source_doctype=None, source_field=None) -> dict:
	require_requester()
	if source_doctype or source_field:
		from srv_erp.masters.dynamic_item.profile import validate_source

		validate_source({"doctype": source_doctype, "fieldname": source_field})
	template, profile = get_template_and_profile(template_item)
	rules = get_profile_rules(profile)
	attributes = []
	template_rows = {
		row.attribute: row for row in template.get("attributes") or [] if not row.disabled and row.attribute
	}
	attribute_names = list(template_rows)
	attribute_names.extend(attribute for attribute in rules if attribute not in template_rows)
	for attribute in attribute_names:
		row = template_rows.get(attribute)
		item_attribute = frappe.get_doc("Item Attribute", attribute)
		rule = rules.get(attribute)
		attributes.append(
			{
				"attribute": attribute,
				"required": bool(rule and cint(rule.required_parameter)),
				"allow_new_values": bool(not rule or cint(rule.allow_new_values)),
				"numeric_values": bool(item_attribute.numeric_values),
				"values": []
				if item_attribute.numeric_values
				else [d.attribute_value for d in item_attribute.item_attribute_values],
				"from_range": row.from_range if row else None,
				"to_range": row.to_range if row else None,
				"increment": row.increment if row else None,
			}
		)
	return {
		"template_item": template.name,
		"stock_uom": template.stock_uom,
		"attributes": attributes,
		"allow_dynamic_attributes": bool(cint(get_settings().allow_dynamic_attributes)),
		"uoms": frappe.get_all("UOM", pluck="name", order_by="name"),
	}


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
	if not is_dynamic_item_enabled() or not user_has_requester_role():
		return {
			"enabled": False,
			"bulk_variant_creation_enabled": is_bulk_variant_creation_enabled(),
			"approval_enforced": bool(cint(settings.enforce_variant_approval)),
			"grids": [],
		}
	grids = [
		{"fieldname": row.table_field, "child_doctype": row.child_doctype}
		for row in settings.get("item_grids") or []
		if cint(row.enabled) and (not document_type or row.document_type == document_type)
	]
	return {
		"enabled": True,
		"bulk_variant_creation_enabled": is_bulk_variant_creation_enabled(),
		"approval_enforced": bool(cint(settings.enforce_variant_approval)),
		"grids": grids,
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
