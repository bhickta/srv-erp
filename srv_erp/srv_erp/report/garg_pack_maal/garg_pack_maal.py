import frappe
from frappe import _
from srv_erp.srv_erp.report.hierarchical_filters import get_descendant_condition

from srv_erp.srv_erp.report.uom_utils import add_selected_uom_columns

def execute(filters=None):
    filters = frappe._dict(filters or {})
    columns = get_columns(filters)
    data = get_data(filters)

    add_selected_uom_columns(
        columns,
        data,
        filters.get("include_uom")
    )

    return columns, data


def get_columns(filters):
    columns = [
        {
            "label": _("Date & Time"),
            "fieldname": "date_time",
            "fieldtype": "Datetime",
            "width": 190,
        },
        {
            "label": _("Item"),
            "fieldname": "item_code",
            "fieldtype": "Link",
            "options": "Item",
            "width": 180,
        },
        {
            "label": _("Item Name"),
            "fieldname": "item_name",
            "fieldtype": "Data",
            "width": 250,
        },
        {
            "label": _("In Qty"),
            "fieldname": "in_qty",
            "fieldtype": "Float",
            "width": 100,
            "convertible": "qty",
        },
        {
            "label": _("Remarks"),
            "fieldname": "remarks",
            "fieldtype": "Small Text",
            "width": 150,
        },
        {
            "label": _("Item Group"),
            "fieldname": "item_group",
            "fieldtype": "Link",
            "options": "Item Group",
            "width": 100,
        },
        {
            "label": _("Rate"),
            "fieldname": "rate",
            "fieldtype": "Currency",
            "width": 110,
        },
        {
            "label": _("Stock Voucher"),
            "fieldname": "stock_voucher",
            "fieldtype": "Link",
            "options": "Stock Entry",
            "width": 160,
        },
        {
            "label": _("Warehouse"),
            "fieldname": "warehouse",
            "fieldtype": "Link",
            "options": "Warehouse",
            "width": 160,
        },
    ]

    return columns

def get_data(filters):
    conditions = [
        "sle.voucher_type = 'Stock Entry'",
        "sle.is_cancelled = 0",
        "sle.actual_qty > 0",
        "sle.posting_date BETWEEN %(from_date)s AND %(to_date)s",
    ]

    values = {
        "from_date": filters.from_date,
        "to_date": filters.to_date,
    }

    if filters.get("company"):
        conditions.append("sle.company = %(company)s")
        values["company"] = filters.company

    if filters.get("stock_entry_type"):
        conditions.append(
            "se.stock_entry_type = %(stock_entry_type)s"
        )
        values["stock_entry_type"] = filters.stock_entry_type

    if filters.get("item_code"):
        conditions.append(
            "sle.item_code = %(item_code)s"
        )
        values["item_code"] = filters.item_code

    if filters.get("item_group"):
        conditions.append(
            get_descendant_condition(
                "Item Group",
                "item.item_group",
                "item_group"
            )
        )
        values["item_group"] = filters.item_group

    if filters.get("warehouse"):
        conditions.append(
            "sle.warehouse = %(warehouse)s"
        )
        values["warehouse"] = filters.warehouse

    return frappe.db.sql(
        f"""
        SELECT
            CONCAT(
                sle.posting_date,
                ' ',
                TIME_FORMAT(sle.posting_time, '%%H:%%i:%%s')
            ) AS date_time,

            sle.item_code AS item_code,

            item.item_name AS item_name,

            item.item_group AS item_group,

            sle.actual_qty AS in_qty,

            sle.stock_uom AS uom,

            sle.incoming_rate AS rate,

            sle.voucher_no AS stock_voucher,

            sed.remarks AS remarks,
            
            sle.warehouse AS warehouse

        FROM `tabStock Ledger Entry` sle

        INNER JOIN `tabStock Entry` se
            ON se.name = sle.voucher_no

        LEFT JOIN `tabStock Entry Detail` sed
            ON sed.name = sle.voucher_detail_no

        LEFT JOIN `tabItem` item
            ON item.name = sle.item_code

        WHERE
            {" AND ".join(conditions)}

        ORDER BY
            sle.posting_date ASC,
            sle.posting_time ASC,
            sle.voucher_no ASC,
            sle.item_code ASC
        """,
        values,
        as_dict=True,
    )