import frappe


OLD_PACKAGE_BARCODE_WORKSPACE = "Package Barcode"
PACKAGE_BARCODE_WORKSPACE = "Package Barcode Tools"


def rename_package_barcode_workspace():
	if frappe.db.exists("Workspace", OLD_PACKAGE_BARCODE_WORKSPACE):
		if frappe.db.exists("Workspace", PACKAGE_BARCODE_WORKSPACE):
			frappe.delete_doc(
				"Workspace",
				OLD_PACKAGE_BARCODE_WORKSPACE,
				force=True,
				ignore_permissions=True,
			)
		else:
			frappe.rename_doc(
				"Workspace",
				OLD_PACKAGE_BARCODE_WORKSPACE,
				PACKAGE_BARCODE_WORKSPACE,
				force=True,
			)

	if frappe.db.exists("Workspace", PACKAGE_BARCODE_WORKSPACE):
		frappe.db.set_value(
			"Workspace",
			PACKAGE_BARCODE_WORKSPACE,
			{
				"label": PACKAGE_BARCODE_WORKSPACE,
				"title": PACKAGE_BARCODE_WORKSPACE,
			},
			update_modified=False,
		)

	frappe.clear_cache()
