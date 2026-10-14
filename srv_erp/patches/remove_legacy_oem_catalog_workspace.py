import frappe


def execute():
    # The workspace used to be named "OEM Catalog", whose slug ("oem-catalog")
    # collided with the OEM Catalog page route, so /app/oem-catalog opened the
    # workspace instead of the configurator page. It is now "OEM Catalogue".
    if frappe.db.exists("Workspace", "OEM Catalog"):
        frappe.delete_doc("Workspace", "OEM Catalog", ignore_permissions=True, force=True)
