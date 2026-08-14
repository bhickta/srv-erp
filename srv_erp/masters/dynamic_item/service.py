from __future__ import annotations

import frappe
from erpnext.controllers.item_variant import get_variant
from frappe import _
from frappe.utils import cint, now_datetime

from srv_erp.masters.dynamic_item.artifact_usage import (
	attribute_used_by_other_request,
	attribute_used_by_template_variant,
	attribute_value_is_referenced,
	brand_is_referenced,
	get_request_artifact_history,
)
from srv_erp.masters.dynamic_item.assignments import (
	assign_request_to_approvers,
	close_approval_assignments,
	require_available_approver,
)
from srv_erp.masters.dynamic_item.cleanup import (
	cleanup_attribute_artifacts,
	cleanup_request_schema,
	delete_staged_item,
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
from srv_erp.masters.dynamic_item.request_flow import (
	create_packaging_request,
	create_variant_request,
	resolve_or_request,
	validate_existing_variant,
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
