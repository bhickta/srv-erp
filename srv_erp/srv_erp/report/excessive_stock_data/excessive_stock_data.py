# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from srv_erp.srv_erp.report.hierarchical_filters import get_descendant_condition


DEFAULT_WAREHOUSE = "Finished Goods - SE"
DEFAULT_BRAND_VARIANT_ATTRIBUTE = "Brand"
RESOLVED_BRAND_SQL = (
    "COALESCE(NULLIF(variant_brand.attribute_value, ''), "
    "NULLIF(item.brand, ''), template.brand)"
)
DELIVERED_STOCK_QTY_SQL = (
    "COALESCE(soi.delivered_qty, 0) "
    "* COALESCE(NULLIF(soi.conversion_factor, 0), 1)"
)
PENDING_STOCK_QTY_SQL = (
    "GREATEST(soi.stock_qty - (" + DELIVERED_STOCK_QTY_SQL + "), 0)"
)


def execute(filters=None):
    filters = frappe._dict(filters or {})
    filters.warehouse = filters.get("warehouse") or DEFAULT_WAREHOUSE
    filters.brand_variant_attribute = (
        frappe.db.get_single_value(
            "SRV Settings", "variant_auto_create_attribute"
        )
        or DEFAULT_BRAND_VARIANT_ATTRIBUTE
    )

    return get_columns(), get_data(filters)


def get_columns():
    return [
        {
            "label": _("Item"),
            "fieldname": "item_code",
            "fieldtype": "Link",
            "options": "Item",
            "width": 130,
        },
        {
            "label": _("Item Name"),
            "fieldname": "item_name",
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "label": _("Item Group"),
            "fieldname": "item_group",
            "fieldtype": "Link",
            "options": "Item Group",
            "width": 140,
        },
        {
            "label": _("Brand"),
            "fieldname": "brand",
            "fieldtype": "Link",
            "options": "Brand",
            "width": 120,
        },
        {
            "label": _("Customers"),
            "fieldname": "customers",
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "label": _("Sales Orders"),
            "fieldname": "sales_orders",
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "label": _("Ordered Qty"),
            "fieldname": "ordered_qty",
            "fieldtype": "Float",
            "width": 110,
        },
        {
            "label": _("Delivered Qty"),
            "fieldname": "delivered_qty",
            "fieldtype": "Float",
            "width": 110,
        },
        {
            "label": _("Pending Qty"),
            "fieldname": "pending_qty",
            "fieldtype": "Float",
            "width": 110,
        },
        {
            "label": _("Current Stock"),
            "fieldname": "current_stock",
            "fieldtype": "Float",
            "width": 120,
        },
        {
            "label": _("Excess Stock"),
            "fieldname": "excess_stock",
            "fieldtype": "Float",
            "width": 120,
        },
        {
            "label": _("UOM"),
            "fieldname": "stock_uom",
            "fieldtype": "Link",
            "options": "UOM",
            "width": 90,
        },
        {
            "label": _("Warehouse"),
            "fieldname": "warehouse",
            "fieldtype": "Link",
            "options": "Warehouse",
            "width": 160,
        },
    ]


def get_data(filters):
    conditions = get_conditions(filters)
    warehouse_condition = get_descendant_condition(
        "Warehouse", "bin_source.warehouse", "warehouse"
    )

    return frappe.db.sql(
        f"""
        SELECT
            soi.item_code,
            MAX(soi.item_name) AS item_name,
            item.item_group,
            {RESOLVED_BRAND_SQL} AS brand,
            GROUP_CONCAT(
                DISTINCT so.customer
                ORDER BY so.customer
                SEPARATOR ', '
            ) AS customers,
            GROUP_CONCAT(
                DISTINCT so.name
                ORDER BY so.name
                SEPARATOR ', '
            ) AS sales_orders,
            SUM(soi.stock_qty) AS ordered_qty,
            SUM({DELIVERED_STOCK_QTY_SQL}) AS delivered_qty,
            SUM({PENDING_STOCK_QTY_SQL}) AS pending_qty,
            MAX(COALESCE(bin.actual_qty, 0)) AS current_stock,
            MAX(COALESCE(bin.actual_qty, 0))
                - SUM({PENDING_STOCK_QTY_SQL}) AS excess_stock,
            item.stock_uom,
            %(warehouse)s AS warehouse
        FROM `tabSales Order Item` soi
        INNER JOIN `tabSales Order` so
            ON so.name = soi.parent
        INNER JOIN `tabItem` item
            ON item.name = soi.item_code
        LEFT JOIN `tabItem` template
            ON template.name = item.variant_of
        LEFT JOIN `tabItem Variant Attribute` variant_brand
            ON variant_brand.parent = item.name
            AND variant_brand.attribute = %(brand_variant_attribute)s
        LEFT JOIN (
            SELECT
                bin_source.item_code,
                SUM(bin_source.actual_qty) AS actual_qty
            FROM `tabBin` bin_source
            WHERE {warehouse_condition}
            GROUP BY bin_source.item_code
        ) bin
            ON bin.item_code = soi.item_code
        WHERE
            so.docstatus = 1
            AND {PENDING_STOCK_QTY_SQL} > 0
            AND {" AND ".join(conditions)}
        GROUP BY
            soi.item_code,
            item.item_group,
            {RESOLVED_BRAND_SQL},
            item.stock_uom
        HAVING
            MAX(COALESCE(bin.actual_qty, 0))
                > SUM({PENDING_STOCK_QTY_SQL})
        ORDER BY
            item_name,
            soi.item_code
        """,
        filters,
        as_dict=True,
    )


def get_conditions(filters):
    conditions = []

    if filters.get("item_code"):
        conditions.append("soi.item_code = %(item_code)s")

    if filters.get("item_group"):
        conditions.append(
            get_descendant_condition(
                "Item Group", "item.item_group", "item_group"
            )
        )

    if filters.get("uom"):
        conditions.append("item.stock_uom = %(uom)s")

    if filters.get("brand"):
        conditions.append(f"{RESOLVED_BRAND_SQL} = %(brand)s")

    if filters.get("customer"):
        conditions.append("so.customer = %(customer)s")

    return conditions or ["1 = 1"]
