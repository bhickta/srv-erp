import frappe


def execute():
	if frappe.db.exists("Custom Field", {"dt": "Sales Order Item", "fieldname": "srv_find_variant"}):
		return

	frappe.get_doc(
		{
			"doctype": "Custom Field",
			"dt": "Sales Order Item",
			"fieldname": "srv_find_variant",
			"label": "Find Variant",
			"fieldtype": "Button",
			"insert_after": "item_code",
			"description": "Choose an item variant using brand, template, and available attributes.",
		}
	).insert(ignore_permissions=True)
