import frappe
from frappe import _

from srv_erp.masters.dynamic_item.configuration import get_approver_users, get_settings


def require_available_approver():
	if get_approver_users(exclude_user=frappe.session.user):
		return
	frappe.throw(
		_("No other enabled System User has the configured approver role {0}.").format(
			frappe.bold(get_settings().approver_role)
		)
	)


def assign_request_to_approvers(request):
	from frappe.desk.form.assign_to import add

	approvers = get_approver_users(exclude_user=request.requested_by)
	if not approvers:
		return
	try:
		add(
			{
				"assign_to": approvers,
				"doctype": request.doctype,
				"name": request.name,
				"description": _("Review {0} for Item template {1}.").format(
					request.request_type, request.template_item
				),
				"priority": "Medium",
				"assigned_by": request.requested_by,
			},
			ignore_permissions=True,
		)
	except Exception:
		frappe.log_error(
			title=_("Dynamic Item Approval Assignment Failed"),
			message=frappe.get_traceback(),
		)


def close_approval_assignments(request):
	from frappe.desk.form.assign_to import remove

	assignments = frappe.get_all(
		"ToDo",
		filters={
			"reference_type": request.doctype,
			"reference_name": request.name,
			"status": ["not in", ["Cancelled", "Closed"]],
		},
		pluck="allocated_to",
	)
	for user in assignments:
		remove(request.doctype, request.name, user, ignore_permissions=True)
