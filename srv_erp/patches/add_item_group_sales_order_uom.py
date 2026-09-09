import frappe


def execute():
    fieldname = "custom_sales_order_uom"
    
    if frappe.db.exists(
        "Custom Field",
        {
            "dt": "Item Group",
            "fieldname": fieldname,
        },
    ):
        return

    custom_field = frappe.get_doc(
        {
            "doctype": "Custom Field",
            "dt": "Item Group",
            "label": "Sales Order UOM",
            "fieldname": fieldname,
            "fieldtype": "Link",
            "options": "UOM",
            "insert_after": "parent_item_group",
            "description": "UOM allowed for this Item Group in Sales Orders.",
        }
    )

    custom_field.insert(ignore_permissions=True)