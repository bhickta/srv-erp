from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import now_datetime

from srv_erp.masters.dynamic_item.assignments import close_approval_assignments
from srv_erp.masters.dynamic_item.cleanup import cleanup_request_schema, delete_staged_item
from srv_erp.masters.dynamic_item.configuration import (
	ADD_PACKAGING,
	APPROVED,
	CANCELLED,
	CREATE_VARIANT,
	PENDING,
	REJECTED,
	require_approver,
	user_has_approver_role,
)
from srv_erp.masters.dynamic_item.context import dynamic_item_service_context
from srv_erp.masters.dynamic_item.item_approval import (
	approve_packaging_request,
	approve_staged_variant,
)
from srv_erp.masters.dynamic_item.normalization import normalize_text
from srv_erp.masters.dynamic_item.repository import lock_request
from srv_erp.masters.dynamic_item.results import approved_result, terminal_result


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
