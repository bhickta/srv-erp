import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.permissions import add_permission, update_permission_property


COLOR_ROLE_PERMISSIONS = {
	"Sales User": ("read", "select"),
	"Sales Manager": ("read", "select", "create", "write", "delete"),
	"System Manager": ("read", "select", "create", "write", "delete"),
}


def create_sales_order_attribute_custom_fields():
	"""Add optional order-level defaults with matching item-level fields."""
	create_custom_fields(
		{
			"Sales Order": [
				{
					"allow_on_submit": 1,
					"fieldname": "branding_type",
					"fieldtype": "Link",
					"insert_after": "delivery_date",
					"label": "Branding Type",
					"options": "Branding Type",
				},
				{
					"allow_on_submit": 1,
					"fieldname": "color",
					"fieldtype": "Link",
					"insert_after": "branding_type",
					"label": "Color",
					"options": "Color",
				},
				{
					"allow_on_submit": 1,
					"fieldname": "marketed_by",
					"fieldtype": "Link",
					"insert_after": "color",
					"label": "Marketed By",
					"options": "Marketed By",
				},
			],
			"Sales Order Item": [
				{
					"allow_on_submit": 1,
					"columns": 1,
					"fieldname": "branding_type",
					"fieldtype": "Link",
					"in_list_view": 1,
					"insert_after": "delivery_date",
					"label": "Branding Type",
					"options": "Branding Type",
				},
				{
					"allow_on_submit": 1,
					"columns": 1,
					"fieldname": "color",
					"fieldtype": "Link",
					"in_list_view": 1,
					"insert_after": "branding_type",
					"label": "Color",
					"options": "Color",
				},
				{
					"allow_on_submit": 1,
					"columns": 1,
					"fieldname": "marketed_by",
					"fieldtype": "Link",
					"in_list_view": 1,
					"insert_after": "color",
					"label": "Marketed By",
					"options": "Marketed By",
				},
			],
		},
		update=True,
	)
	ensure_color_permissions()


def ensure_color_permissions():
	"""Make the standard Color master usable from the sales transaction fields."""
	if not frappe.db.exists("DocType", "Color"):
		return

	for role, permission_types in COLOR_ROLE_PERMISSIONS.items():
		filters = {
			"parent": "Color",
			"role": role,
			"permlevel": 0,
			"if_owner": 0,
		}
		if not frappe.db.exists("Custom DocPerm", filters):
			add_permission("Color", role, ptype="read")

		for permission_type in permission_types:
			update_permission_property("Color", role, 0, permission_type, 1)
