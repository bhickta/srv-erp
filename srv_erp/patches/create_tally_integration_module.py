import frappe


def execute():
	if frappe.db.exists("Module Def", "Tally Integration"):
		return

	frappe.get_doc(
		{
			"doctype": "Module Def",
			"module_name": "Tally Integration",
			"app_name": "srv_erp",
			"custom": 0,
		}
	).insert(ignore_permissions=True)
