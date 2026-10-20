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
	table = "`tabSRV Production Entry`"
	if is_planner(user):
		return _company_condition(table, user)
	allowed = assignment_query(user)
	return (
		f"((EXISTS (SELECT 1 FROM `tabSRV Production Entry Item` i WHERE i.parent={table}.name) "
		"AND NOT EXISTS (SELECT 1 FROM `tabSRV Production Entry Item` i "
		"LEFT JOIN `tabSRV Production Assignment` ON `tabSRV Production Assignment`.name=i.assignment "
		f"WHERE i.parent={table}.name AND (`tabSRV Production Assignment`.name IS NULL OR NOT ({allowed})))) "
		f"OR (NOT EXISTS (SELECT 1 FROM `tabSRV Production Entry Item` i WHERE i.parent={table}.name) "
		"AND EXISTS (SELECT 1 FROM `tabSRV Production Assignment` "
		f"WHERE `tabSRV Production Assignment`.name={table}.assignment AND {allowed})))"
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
	names = {row.assignment for row in (doc.get("items") or []) if row.assignment}
	if not names and doc.get("assignment"):
		names.add(doc.assignment)
	if not names:
		return ptype == "create" and (is_planner(user) or SUPERVISOR in frappe.get_roles(user))
	for name in names:
		assignment = frappe.db.get_value(
			"SRV Production Assignment", name, ["company", "supervisor"], as_dict=True
		)
		if not assignment or not assignment_permission(assignment, "read", user):
			return False
	if is_planner(user):
		return True
	return SUPERVISOR in frappe.get_roles(user) and ptype in (
		"read",
		"select",
		"create",
		"write",
		"submit",
		"print",
		"report",
		"export",
	)


def prevent_production_sharing(doc, method=None):
	# Frappe v15 shares can bypass both query and document permission hooks.
	# Production visibility is therefore managed exclusively by supervisor/role.
	if doc.share_doctype in (
		"SRV Production Schedule",
		"SRV Production Assignment",
		"SRV Production Entry",
		"SRV Production Schedule Item",
		"SRV Production Schedule Responsibility",
		"SRV Production Entry Item",
	):
		frappe.throw(
			frappe._("Production records cannot be shared. Change the assignment supervisor instead."),
			frappe.PermissionError,
		)


def schedule_item_query(user=None):
	return (
		"EXISTS (SELECT 1 FROM `tabSRV Production Schedule` "
		"WHERE `tabSRV Production Schedule`.name=`tabSRV Production Schedule Item`.parent "
		f"AND {schedule_query(user)})"
	)


def entry_item_query(user=None):
	# Child-table APIs check parent DocType access, not its document-level filter.
	return (
		"EXISTS (SELECT 1 FROM `tabSRV Production Entry` "
		"WHERE `tabSRV Production Entry`.name=`tabSRV Production Entry Item`.parent "
		f"AND {entry_query(user)})"
	)


def responsibility_query(user=None):
	return (
		"EXISTS (SELECT 1 FROM `tabSRV Production Schedule` "
		"WHERE `tabSRV Production Schedule`.name=`tabSRV Production Schedule Responsibility`.parent "
		f"AND {schedule_query(user)})"
	)
