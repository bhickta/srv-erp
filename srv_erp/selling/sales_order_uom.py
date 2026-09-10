import frappe


def get_sales_order_uom(item_group):
    hierarchy = []

    while item_group:
        hierarchy.append(item_group)

        item_group = frappe.db.get_value(
            "Item Group",
            item_group,
            "parent_item_group",
        )

    for group_name in reversed(hierarchy):
        sales_order_uom = frappe.db.get_value(
            "Item Group",
            group_name,
            "custom_sales_order_uom",
        )

        if sales_order_uom:
            return sales_order_uom, group_name

    return None, None


def validate_sales_order_uom(doc, method=None):
    for row in doc.items:
        if not row.item_code:
            continue

        item_group = frappe.db.get_value(
            "Item",
            row.item_code,
            "item_group",
        )

        if not item_group:
            continue

        allowed_uom, group_name = get_sales_order_uom(item_group)

        if not allowed_uom:
            continue

        if row.uom != allowed_uom:
            frappe.throw(
                f"Item <b>{row.item_code}</b> belongs to "
                f"Item Group <b>{group_name}</b>. "
                f"The allowed Sales Order UOM is "
                f"<b>{allowed_uom}</b>."
            )