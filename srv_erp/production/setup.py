import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.permissions import add_permission

from srv_erp.production.permissions import PLANNER, SUPERVISOR


def ensure_roles():
	for role in (PLANNER, SUPERVISOR):
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
				ignore_permissions=True
			)


def setup_production():
	ensure_roles()
	ensure_operation("Production")
	# These roles need item/UOM selection without granting general stock entry access.
	for role in (PLANNER, SUPERVISOR):
		for doctype, ptype in (
			("Item", "read"),
			("UOM", "read"),
			("Company", "read"),
			("User", "select"),
			("Operation", "select"),
		):
			if not frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0}):
				add_permission(doctype, role, ptype=ptype)
	create_custom_fields(
		{
			"Item": [
				{
					"fieldname": "custom_production_supervisor",
					"fieldtype": "Link",
					"label": "Production Supervisor",
					"options": "User",
					"insert_after": "has_variants",
					"depends_on": "eval:doc.has_variants",
					"no_copy": 1,
					"description": "Default responsible user for new production schedules of this template.",
				}
			]
		},
		update=True,
	)


def validate_supervisor(user):
	if not user or not frappe.db.exists("User", {"name": user, "enabled": 1, "user_type": "System User"}):
		frappe.throw(_("Select an enabled system user as Production Supervisor."))
	if SUPERVISOR not in frappe.get_roles(user):
		frappe.throw(_("The responsible user must have the SRV Production Supervisor role."))


def validate_item_supervisor(doc, method=None):
	if doc.has_variants and doc.get("custom_production_supervisor"):
		validate_supervisor(doc.custom_production_supervisor)


def ensure_operation(name):
	"""Keep existing production labels usable when converting Data to Link."""
	if not frappe.db.exists("Operation", name):
		frappe.get_doc({"doctype": "Operation", "name": name}).insert(ignore_permissions=True)
