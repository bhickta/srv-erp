import frappe
from frappe.core.doctype.user_permission.user_permission import get_user_permissions

PLANNER = "SRV Production Planner"
SUPERVISOR = "SRV Production Supervisor"


def is_planner(user=None):
	user = user or frappe.session.user
	return user == "Administrator" or bool({PLANNER, "System Manager"} & set(frappe.get_roles(user)))


def company_allowed(company, user=None):
	permissions = get_user_permissions(user or frappe.session.user).get("Company", [])
	return not permissions or company in {row.doc for row in permissions}


def _company_condition(table, user):
	permissions = get_user_permissions(user).get("Company", [])
	if not permissions:
		return "1=1"
	values = ", ".join(frappe.db.escape(row.doc) for row in permissions)
	return f"{table}.company IN ({values})"


def assignment_query(user=None):
	user = user or frappe.session.user
	table = "`tabSRV Production Assignment`"
	condition = _company_condition(table, user)
	if not is_planner(user):
		condition += f" AND {table}.supervisor = {frappe.db.escape(user)}"
	return condition


def schedule_query(user=None):
	user = user or frappe.session.user
	return _company_condition("`tabSRV Production Schedule`", user) if is_planner(user) else "1=0"


def entry_query(user=None):
	user = user or frappe.session.user
	return (
		"EXISTS (SELECT 1 FROM `tabSRV Production Assignment` "
		"WHERE `tabSRV Production Assignment`.name = `tabSRV Production Entry`.assignment "
		f"AND {assignment_query(user)})"
	)


def assignment_permission(doc, ptype, user=None, **kwargs):
	user = user or frappe.session.user
	if not company_allowed(doc.company, user):
		return False
	if is_planner(user):
		return True
	return (
		SUPERVISOR in frappe.get_roles(user)
		and doc.supervisor == user
		and ptype in ("read", "select", "print", "report", "export")
	)


def schedule_permission(doc, ptype, user=None, **kwargs):
	return is_planner(user) and company_allowed(doc.company, user)


def entry_permission(doc, ptype, user=None, **kwargs):
	user = user or frappe.session.user
	if not doc.assignment:
		return ptype == "create" and (is_planner(user) or SUPERVISOR in frappe.get_roles(user))
	assignment = frappe.db.get_value(
		"SRV Production Assignment", doc.assignment, ["company", "supervisor"], as_dict=True
	)
	if not assignment or not company_allowed(assignment.company, user):
		return False
	if is_planner(user):
		return True
	return (
		SUPERVISOR in frappe.get_roles(user)
		and assignment.supervisor == user
		and ptype in ("read", "select", "create", "write", "submit", "print", "report", "export")
	)


def prevent_production_sharing(doc, method=None):
	# Frappe v15 shares can bypass both query and document permission hooks.
	# Production visibility is therefore managed exclusively by supervisor/role.
	if doc.share_doctype in ("SRV Production Schedule", "SRV Production Assignment", "SRV Production Entry"):
		frappe.throw(
			frappe._("Production records cannot be shared. Change the assignment supervisor instead."),
			frappe.PermissionError,
		)
