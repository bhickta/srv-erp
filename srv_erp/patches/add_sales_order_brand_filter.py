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
            "label": "Brand / Marka",
            "fieldtype": "Link",
            "options": "Brand",
            "insert_after": "customer",
        }
    ).insert(ignore_permissions=True)