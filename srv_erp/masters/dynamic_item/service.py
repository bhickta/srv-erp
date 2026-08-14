from __future__ import annotations

import frappe
from erpnext.controllers.item_variant import get_variant
from frappe import _
from frappe.utils import cint, now_datetime

from srv_erp.masters.dynamic_item.assignments import (
	assign_request_to_approvers,
	close_approval_assignments,
	require_available_approver,
)
from srv_erp.masters.dynamic_item.configuration import (
	ADD_PACKAGING,
	APPROVED,
	CANCELLED,
	CREATE_VARIANT,
	PENDING,
	REJECTED,
	get_settings,
	require_approver,
	require_requester,
	user_has_approver_role,
)
from srv_erp.masters.dynamic_item.context import dynamic_item_service_context
from srv_erp.masters.dynamic_item.exceptions import DynamicItemConflict
from srv_erp.masters.dynamic_item.lookups import (
	canonicalize_known_masters,
)
from srv_erp.masters.dynamic_item.normalization import (
	normalize_attributes,
	normalize_text,
	normalize_uoms,
	parse_payload,
)
from srv_erp.masters.dynamic_item.packaging import (
	add_packaging_rows,
	get_missing_packaging,
	validate_no_overlapping_packaging_request,
)
from srv_erp.masters.dynamic_item.profile import (
	get_profile_rules,
	get_template_and_profile,
	validate_requested_attributes,
	validate_source,
)
from srv_erp.masters.dynamic_item.repository import (
	get_item_state,
	get_pending_request,
	get_variant_if_present,
	insert_request,
	lock_request,
	lock_template,
)
from srv_erp.masters.dynamic_item.results import (
	approved_result,
	existing_result,
	request_result,
	terminal_result,
)
from srv_erp.masters.dynamic_item.signatures import (
	make_identity_signature,
	make_packaging_signature,
)
from srv_erp.masters.dynamic_item.staging import (
	stage_requested_schema,
	stage_variant_item,
)


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


def get_request_attributes(request) -> dict[str, str]:
	return {row.item_attribute: row.attribute_value for row in request.attributes}


def approve_request(name: str) -> dict:
	require_approver()
	lock_request(name)
	request = frappe.get_doc("Dynamic Item Request", name)
	if request.status == APPROVED:
		return approved_result(request)
	if request.status != PENDING:
		frappe.throw(_("Only Pending Approval requests can be approved."))
	if request.requested_by == frappe.session.user:
		frappe.throw(_("Requesters cannot approve their own Dynamic Item Request."), frappe.PermissionError)

	if request.request_type == CREATE_VARIANT:
		resolved_item = approve_staged_variant(request)
	elif request.request_type == ADD_PACKAGING:
		resolved_item = approve_packaging_request(request)
	else:
		frappe.throw(_("Unsupported Dynamic Item Request type {0}.").format(request.request_type))

	request.status = APPROVED
	request.active_signature = None
	request.resolved_item = resolved_item
	request.approved_by = frappe.session.user
	request.approved_on = now_datetime()
	with dynamic_item_service_context():
		request.save(ignore_permissions=True)
	close_approval_assignments(request)
	request.add_comment("Info", _("Approved and resolved to Item {0}.").format(resolved_item))
	return approved_result(request)


def approve_staged_variant(request) -> str:
	if not request.staged_item_code or not frappe.db.exists("Item", request.staged_item_code):
		frappe.throw(_("The staged Item no longer exists."))
	lock_template(request.template_item)
	attributes = get_request_attributes(request)
	other_variant = get_variant(request.template_item, attributes, variant=request.staged_item_code)
	if other_variant:
		state = get_item_state(other_variant)
		if cint(state.disabled):
			frappe.throw(
				_("Matching Item {0} exists but is disabled.").format(frappe.bold(other_variant)),
				DynamicItemConflict,
			)
		delete_staged_item(request)
		return other_variant

	item = frappe.get_doc("Item", request.staged_item_code)
	if item.dynamic_item_approval_status != PENDING or item.dynamic_item_request != request.name:
		frappe.throw(_("Staged Item approval metadata does not match this request."))
	if not cint(item.disabled):
		frappe.throw(_("Staged Item must remain disabled until approval."))
	missing_packaging = get_missing_packaging(item, [row.as_dict() for row in request.uoms])
	if missing_packaging:
		frappe.throw(_("Staged Item packaging no longer matches the approved request parameters."))
	item.dynamic_item_approval_status = APPROVED
	item.dynamic_item_approved_by = frappe.session.user
	item.dynamic_item_approved_on = now_datetime()
	item.disabled = 0
	with dynamic_item_service_context():
		item.save(ignore_permissions=True)
	return item.name


def approve_packaging_request(request) -> str:
	if not request.resolved_item or not frappe.db.exists("Item", request.resolved_item):
		frappe.throw(_("The Item for this packaging request no longer exists."))
	frappe.db.sql("select name from `tabItem` where name = %s for update", request.resolved_item)
	item = frappe.get_doc("Item", request.resolved_item)
	if cint(item.disabled):
		frappe.throw(_("Item {0} is disabled.").format(frappe.bold(item.name)))
	add_packaging_rows(item, [row.as_dict() for row in request.uoms])
	with dynamic_item_service_context():
		item.save(ignore_permissions=True)
	return item.name


def reject_request(name: str, reason: str) -> dict:
	require_approver()
	reason = normalize_text(reason, _("Rejection Reason"))
	lock_request(name)
	request = frappe.get_doc("Dynamic Item Request", name)
	if request.status == REJECTED:
		return terminal_result(request)
	if request.status != PENDING:
		frappe.throw(_("Only Pending Approval requests can be rejected."))
	return terminate_request(request, REJECTED, reason, frappe.session.user)


def cancel_request(name: str, reason: str | None = None) -> dict:
	lock_request(name)
	request = frappe.get_doc("Dynamic Item Request", name)
	if request.status == CANCELLED:
		return terminal_result(request)
	if request.status != PENDING:
		frappe.throw(_("Only Pending Approval requests can be cancelled."))
	if request.requested_by != frappe.session.user and "System Manager" not in frappe.get_roles():
		frappe.throw(
			_("Only the requester or a System Manager can cancel this request."), frappe.PermissionError
		)
	return terminate_request(
		request,
		CANCELLED,
		normalize_text(reason or _("Cancelled by requester"), _("Cancellation Reason")),
		frappe.session.user,
	)


def terminate_request(request, status: str, reason: str, actor: str) -> dict:
	if request.request_type == CREATE_VARIANT:
		delete_staged_item(request)
		cleanup_request_schema(request)
	request.status = status
	request.active_signature = None
	request.rejection_reason = reason
	request.rejected_by = actor
	request.rejected_on = now_datetime()
	request.staged_item_code = None
	with dynamic_item_service_context():
		request.save(ignore_permissions=True)
	close_approval_assignments(request)
	request.add_comment("Info", _("{0}: {1}").format(status, reason))
	return terminal_result(request)


def delete_staged_item(request):
	item_code = request.staged_item_code
	if not item_code or not frappe.db.exists("Item", item_code):
		return
	links = frappe.get_all(
		"Dynamic Item Request",
		filters={"resolved_item": item_code, "name": ["!=", request.name]},
		pluck="name",
		limit=1,
	)
	if links:
		frappe.throw(_("Staged Item {0} is referenced by another request.").format(frappe.bold(item_code)))
	with dynamic_item_service_context():
		frappe.delete_doc("Item", item_code, ignore_permissions=True)


def cleanup_request_schema(request):
	for row in reversed(request.attributes):
		try:
			cleanup_attribute_artifacts(request, row)
		except Exception:
			frappe.log_error(
				title=_("Dynamic Item Schema Cleanup Failed"),
				message=frappe.get_traceback(),
			)


def cleanup_attribute_artifacts(request, row):
	attribute = row.item_attribute
	value = row.attribute_value
	history = get_request_artifact_history(request.template_item, attribute, value)
	if (
		history.template_link_created
		and not history.template_adopted
		and not attribute_used_by_other_request(request.name, request.template_item, attribute)
	):
		if not attribute_used_by_template_variant(request.template_item, attribute):
			template = frappe.get_doc("Item", request.template_item)
			template.set("attributes", [d for d in template.attributes if d.attribute != attribute])
			template.flags.dont_update_variants = True
			with dynamic_item_service_context():
				template.save(ignore_permissions=True)

	if (
		history.profile_row_created
		and not history.template_adopted
		and frappe.db.exists("Dynamic Variant Profile", request.template_item)
	):
		profile = frappe.get_doc("Dynamic Variant Profile", request.template_item)
		profile_row = next((d for d in profile.attributes if d.item_attribute == attribute), None)
		if (
			profile_row
			and not cint(profile_row.required_parameter)
			and cint(profile_row.allow_new_values)
			and not attribute_used_by_other_request(request.name, request.template_item, attribute)
		):
			profile.set("attributes", [d for d in profile.attributes if d.item_attribute != attribute])
			with dynamic_item_service_context():
				profile.save(ignore_permissions=True)

	if (
		history.value_created
		and not history.value_adopted
		and not attribute_value_is_referenced(request.name, attribute, value)
	):
		item_attribute = frappe.get_doc("Item Attribute", attribute)
		item_attribute.set(
			"item_attribute_values",
			[d for d in item_attribute.item_attribute_values if d.attribute_value != value],
		)
		with dynamic_item_service_context():
			item_attribute.save(ignore_permissions=True)

	if history.master_created and not history.value_adopted and attribute.casefold() == "brand":
		if frappe.db.exists("Brand", value) and not brand_is_referenced(value):
			with dynamic_item_service_context():
				frappe.delete_doc("Brand", value, ignore_permissions=True)

	if (
		history.attribute_created
		and not history.attribute_adopted
		and frappe.db.exists("Item Attribute", attribute)
	):
		if not frappe.db.exists("Item Variant Attribute", {"attribute": attribute}) and not frappe.db.exists(
			"Item Attribute Value", {"parent": attribute}
		):
			with dynamic_item_service_context():
				frappe.delete_doc("Item Attribute", attribute, ignore_permissions=True)


def get_request_artifact_history(template: str, attribute: str, value: str) -> frappe._dict:
	rows = frappe.db.sql(
		"""
		select
			max(attribute_row.attribute_was_created) as attribute_created,
			max(
				case when request.status = %(approved)s then 1 else 0 end
			) as attribute_adopted,
			max(
				case when request.template_item = %(template)s
				then attribute_row.template_link_was_created else 0 end
			) as template_link_created,
			max(
				case when request.template_item = %(template)s
					and request.status = %(approved)s then 1 else 0 end
			) as template_adopted,
			max(
				case when request.template_item = %(template)s
				then attribute_row.profile_row_was_created else 0 end
			) as profile_row_created,
			max(
				case when attribute_row.attribute_value = %(value)s
				then attribute_row.value_was_created else 0 end
			) as value_created,
			max(
				case when attribute_row.attribute_value = %(value)s
					and request.status = %(approved)s then 1 else 0 end
			) as value_adopted,
			max(
				case when attribute_row.attribute_value = %(value)s
				then attribute_row.master_was_created else 0 end
			) as master_created
		from `tabDynamic Item Request Attribute` attribute_row
		inner join `tabDynamic Item Request` request on request.name = attribute_row.parent
		where attribute_row.item_attribute = %(attribute)s
		""",
		{
			"approved": APPROVED,
			"template": template,
			"attribute": attribute,
			"value": value,
		},
		as_dict=True,
	)
	return frappe._dict(rows[0] if rows else {})


def attribute_used_by_template_variant(template: str, attribute: str) -> bool:
	return bool(
		frappe.db.sql(
			"""
			select 1
			from `tabItem Variant Attribute` attribute_row
			inner join `tabItem` item on item.name = attribute_row.parent
			where item.variant_of = %(template)s
				and attribute_row.attribute = %(attribute)s
			limit 1
			""",
			{"template": template, "attribute": attribute},
		)
	)


def attribute_used_by_other_request(request_name: str, template: str, attribute: str) -> bool:
	return bool(
		frappe.db.sql(
			"""
			select 1
			from `tabDynamic Item Request Attribute` attribute_row
			inner join `tabDynamic Item Request` request on request.name = attribute_row.parent
			where request.name != %(request_name)s
				and request.template_item = %(template)s
				and request.status = %(pending)s
				and attribute_row.item_attribute = %(attribute)s
			limit 1
			""",
			{
				"request_name": request_name,
				"template": template,
				"pending": PENDING,
				"attribute": attribute,
			},
		)
	)


def attribute_value_is_referenced(request_name: str, attribute: str, value: str) -> bool:
	if frappe.db.exists(
		"Item Variant Attribute",
		{"attribute": attribute, "attribute_value": value},
	):
		return True
	return bool(
		frappe.db.sql(
			"""
			select 1
			from `tabDynamic Item Request Attribute` attribute_row
			inner join `tabDynamic Item Request` request on request.name = attribute_row.parent
			where request.name != %(request_name)s
				and request.status = %(pending)s
				and attribute_row.item_attribute = %(attribute)s
				and attribute_row.attribute_value = %(value)s
			limit 1
			""",
			{
				"request_name": request_name,
				"pending": PENDING,
				"attribute": attribute,
				"value": value,
			},
		)
	)


def brand_is_referenced(brand: str) -> bool:
	if frappe.db.exists("Item", {"brand": brand}):
		return True
	return frappe.db.exists(
		"Item Variant Attribute",
		{"attribute": "Brand", "attribute_value": brand},
	)


def get_request_status(name: str) -> dict:
	request = frappe.get_doc("Dynamic Item Request", name)
	if request.requested_by != frappe.session.user and not (
		"System Manager" in frappe.get_roles() or user_has_approver_role()
	):
		frappe.throw(_("Not permitted to view this request."), frappe.PermissionError)
	can_review = request.status == PENDING and user_has_approver_role()
	return {
		"name": request.name,
		"request_type": request.request_type,
		"status": request.status,
		"item_code": request.resolved_item or request.staged_item_code,
		"can_approve": can_review and request.requested_by != frappe.session.user,
		"can_reject": can_review,
		"can_cancel": request.status == PENDING and request.requested_by == frappe.session.user,
	}
