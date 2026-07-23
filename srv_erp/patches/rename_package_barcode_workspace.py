import frappe


OLD_WORKSPACE = "Package Barcode"
NEW_WORKSPACE = "Package Barcode Tools"


def execute():
	if frappe.db.exists("Workspace", OLD_WORKSPACE):
		if frappe.db.exists("Workspace", NEW_WORKSPACE):
			frappe.delete_doc(
				"Workspace",
				OLD_WORKSPACE,
				force=True,
				ignore_permissions=True,
			)
		else:
			frappe.rename_doc(
				"Workspace",
				OLD_WORKSPACE,
				NEW_WORKSPACE,
				force=True,
			)

	if frappe.db.exists("Workspace", NEW_WORKSPACE):
		frappe.db.set_value(
			"Workspace",
			NEW_WORKSPACE,
			{
				"label": NEW_WORKSPACE,
				"title": NEW_WORKSPACE,
			},
			update_modified=False,
		)

	frappe.clear_cache()
