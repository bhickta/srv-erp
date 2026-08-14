from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from srv_erp.masters.dynamic_item.assignments import (
	assign_request_to_approvers,
	require_available_approver,
)
from srv_erp.masters.dynamic_item.configuration import (
	ADD_PACKAGING,
	CREATE_VARIANT,
	PENDING,
	require_requester,
)
from srv_erp.masters.dynamic_item.context import dynamic_item_service_context
from srv_erp.masters.dynamic_item.exceptions import DynamicItemConflict
from srv_erp.masters.dynamic_item.lookups import canonicalize_known_masters
from srv_erp.masters.dynamic_item.normalization import normalize_attributes, normalize_uoms, parse_payload
from srv_erp.masters.dynamic_item.packaging import (
	get_missing_packaging,
	validate_no_overlapping_packaging_request,
)
from srv_erp.masters.dynamic_item.profile import (
	get_template_and_profile,
	validate_requested_attributes,
	validate_source,
)
from srv_erp.masters.dynamic_item.repository import (
	get_item_state,
	get_pending_request,
	get_variant_if_present,
	insert_request,
	lock_template,
)
from srv_erp.masters.dynamic_item.results import existing_result, request_result
from srv_erp.masters.dynamic_item.signatures import make_identity_signature, make_packaging_signature
from srv_erp.masters.dynamic_item.staging import stage_requested_schema, stage_variant_item


def resolve_or_request(payload) -> dict:
	require_requester()
	payload = parse_payload(payload)
	source = validate_source(payload.get("source"))
	attributes = canonicalize_known_masters(normalize_attributes(payload.get("attributes")))
	uoms = normalize_uoms(payload.get("uoms"))
	template, profile = get_template_and_profile(payload.get("template_item"))
	validate_requested_attributes(template, profile, attributes)

	identity_signature = make_identity_signature(template.name, attributes)
	existing_variant = get_variant_if_present(template.name, attributes)
	if existing_variant:
		pending_result = validate_existing_variant(existing_variant)
		if pending_result:
			return pending_result
		item = frappe.get_doc("Item", existing_variant)
		missing_uoms = get_missing_packaging(item, uoms)
		if not missing_uoms:
			return existing_result(item.name)
		return create_packaging_request(item, template, attributes, missing_uoms, source)

	return create_variant_request(template, profile, attributes, uoms, source, identity_signature)


def validate_existing_variant(item_code: str):
	state = get_item_state(item_code)
	if not state:
		return
	if state.dynamic_item_approval_status == PENDING and state.dynamic_item_request:
		request = frappe.get_doc("Dynamic Item Request", state.dynamic_item_request)
		return request_result(request)
	if cint(state.disabled):
		frappe.throw(
			_("Matching Item {0} exists but is disabled; reactivate or resolve it in Masters.").format(
				frappe.bold(item_code)
			),
			DynamicItemConflict,
		)
	return None


def create_packaging_request(item, template, attributes, uoms, source) -> dict:
	require_available_approver()
	signature = make_packaging_signature(item.name, uoms)
	active_signature = f"packaging:{signature}"
	existing = get_pending_request(active_signature)
	if existing:
		return request_result(frappe.get_doc("Dynamic Item Request", existing.name))
	validate_no_overlapping_packaging_request(item.name, uoms)
	request, created = insert_request(
		{
			"request_type": ADD_PACKAGING,
			"status": PENDING,
			"template_item": template.name,
			"resolved_item": item.name,
			"signature": signature,
			"active_signature": active_signature,
			"source_doctype": source.get("doctype"),
			"source_field": source.get("fieldname"),
			"source_name": source.get("document"),
			"requested_by": frappe.session.user,
			"requested_on": now_datetime(),
			"attributes": [
				{"item_attribute": attribute, "attribute_value": value}
				for attribute, value in attributes.items()
			],
			"uoms": uoms,
		}
	)
	if created:
		request.add_comment("Info", _("Packaging addition requested for Item {0}.").format(item.name))
		assign_request_to_approvers(request)
	return request_result(request, created=created)


def create_variant_request(template, profile, attributes, uoms, source, identity_signature) -> dict:
	require_available_approver()
	request, created = insert_request(
		{
			"request_type": CREATE_VARIANT,
			"status": PENDING,
			"template_item": template.name,
			"signature": identity_signature,
			"active_signature": f"variant:{identity_signature}",
			"source_doctype": source.get("doctype"),
			"source_field": source.get("fieldname"),
			"source_name": source.get("document"),
			"requested_by": frappe.session.user,
			"requested_on": now_datetime(),
			"attributes": [
				{"item_attribute": attribute, "attribute_value": value}
				for attribute, value in attributes.items()
			],
			"uoms": uoms,
		}
	)
	if not created:
		return request_result(request)

	lock_template(template.name)
	request = frappe.get_doc("Dynamic Item Request", request.name)
	canonical_attributes = stage_requested_schema(request, template, profile)
	request.signature = make_identity_signature(template.name, canonical_attributes)
	stage_variant_item(request, template, canonical_attributes, request.signature)
	with dynamic_item_service_context():
		request.save(ignore_permissions=True)
	request.add_comment("Info", _("Disabled Item {0} staged for approval.").format(request.staged_item_code))
	assign_request_to_approvers(request)
	return request_result(request, created=True)
