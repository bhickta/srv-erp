import frappe


def execute():
    if frappe.db.exists(
        "Custom Field",
        {
            "dt": "Sales Order",
            "fieldname": "brand_filter",
        },
    ):
        return

    frappe.get_doc(
        {
            "doctype": "Custom Field",
            "dt": "Sales Order",
            "fieldname": "brand_filter",
            "label": "Select Brand",
            "fieldtype": "Link",
            "options": "Brand",
            "insert_after": "items_section",
            "description": "Select a brand to show only its items."
        }
    ).insert(ignore_permissions=True)