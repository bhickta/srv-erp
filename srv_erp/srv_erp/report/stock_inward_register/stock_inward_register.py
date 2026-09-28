# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate

from srv_erp.srv_erp.report.hierarchical_filters import get_descendant_condition
from srv_erp.srv_erp.report.uom_utils import add_selected_uom_columns


INWARD_VOUCHER_TYPES = ("Purchase Receipt", "Stock Entry")


def execute(filters=None):
    filters = frappe._dict(filters or {})

    validate_filters(filters)

    columns = get_columns(filters)
    data = get_data(filters)
    add_selected_uom_columns(columns, data, filters.get("include_uom"))
    report_summary = get_report_summary(data)

    return columns, data, None, None, report_summary


def validate_filters(filters):
    if not filters.get("company"):
        frappe.throw(_("Company is required."))

    if not filters.get("from_date") or not filters.get("to_date"):
        frappe.throw(_("From Date and To Date are required."))

    if getdate(filters.from_date) > getdate(filters.to_date):
        frappe.throw(_("From Date cannot be after To Date."))

    if (
        filters.get("voucher_type")
        and filters.voucher_type not in INWARD_VOUCHER_TYPES
    ):
        frappe.throw(
            _("Voucher Type must be Purchase Receipt or Stock Entry.")
        )

    if filters.get("voucher_no") and not filters.get("voucher_type"):
        frappe.throw(
            _("Please select a Voucher Type before selecting a Voucher.")
        )


def get_columns(filters):
    columns = [
        {
            "label": _("Brand"),
            "fieldname": "brand",
            "fieldtype": "Data",
            "width": 140,
        },
        {
            "label": _("Item Code"),
            "fieldname": "item_code",
            "fieldtype": "Data",
            "width": 160,
        },
        {
            "label": _("Item Name"),
            "fieldname": "item_name",
            "fieldtype": "Data",
            "width": 250,
        },
        {
            "label": _("Inward Qty"),
            "fieldname": "in_qty",
            "fieldtype": "Float",
            "width": 130,
            "convertible": "qty",
        },
        {
            "label": _("Voucher"),
            "fieldname": "voucher",
            "fieldtype": "Data",
            "width": 120,
        },
    ]

    if filters.get("price_list"):
        columns.append(
            {
                "label": _("Basic Rate"),
                "fieldname": "basic_rate",
                "fieldtype": "Currency",
                "options": "company_currency",
                "width": 120,
            }
        )

    columns.extend(
        [
            {
                "label": _("Supplier"),
                "fieldname": "supplier",
                "fieldtype": "Link",
                "options": "Supplier",
                "width": 150,
            },
            {
                "label": _("Supplier Name"),
                "fieldname": "supplier_name",
                "fieldtype": "Data",
                "width": 200,
            },
            {
                "label": _("Stock UOM"),
                "fieldname": "stock_uom",
                "fieldtype": "Link",
                "options": "UOM",
                "width": 100,
            },
            {
                "label": _("Inward Qty UOM"),
                "fieldname": "uom_in_qty",
                "fieldtype": "Link",
                "options": "UOM",
                "hidden": 1,
            },
            {
                "label": _("Stock Value"),
                "fieldname": "stock_value",
                "fieldtype": "Currency",
                "options": "company_currency",
                "width": 130,
            },
            {
                "label": _("Company"),
                "fieldname": "company",
                "fieldtype": "Link",
                "options": "Company",
                "hidden": 1,
            },
            {
                "label": _("Currency"),
                "fieldname": "company_currency",
                "fieldtype": "Link",
                "options": "Currency",
                "hidden": 1,
            },
            {
                "label": _("Voucher Data"),
                "fieldname": "vouchers",
                "fieldtype": "Data",
                "hidden": 1,
            },
            {
                "label": _("Voucher Count"),
                "fieldname": "voucher_count",
                "fieldtype": "Int",
                "hidden": 1,
            },
        ]
    )

    return columns


def get_data(filters):
    conditions = get_conditions(filters)

    basic_rate_field = "0 AS basic_rate"

    if filters.get("price_list"):
        basic_rate_field = """
            COALESCE(
                (
                    SELECT ip.price_list_rate
                    FROM `tabItem Price` ip
                    WHERE
                        ip.item_code = sle.item_code
                        AND ip.price_list = %(price_list)s
                        AND (
                            ip.valid_from IS NULL
                            OR ip.valid_from <= %(to_date)s
                        )
                        AND (
                            ip.valid_upto IS NULL
                            OR ip.valid_upto >= %(to_date)s
                        )
                    ORDER BY
                        ip.valid_from DESC,
                        ip.creation DESC
                    LIMIT 1
                ),
                0
            ) AS basic_rate
        """

    rows = frappe.db.sql(
        f"""
        SELECT
            COALESCE(
                iva.attribute_value,
                ''
            ) AS brand,

            COALESCE(
                item.variant_of,
                sle.item_code
            ) AS item_code,

            item.item_name AS item_name,

            SUM(sle.actual_qty) AS in_qty,

            COUNT(
                DISTINCT CONCAT(
                    sle.voucher_type,
                    '::',
                    sle.voucher_no
                )
            ) AS voucher_count,

            GROUP_CONCAT(
                DISTINCT CONCAT(
                    sle.voucher_type,
                    '::',
                    sle.voucher_no
                )
                ORDER BY
                    sle.voucher_no
                SEPARATOR '||'
            ) AS vouchers,

            {basic_rate_field},

            COALESCE(
                pr.supplier,
                se.supplier,
                ''
            ) AS supplier,

            COALESCE(
                pr.supplier_name,
                se.supplier_name,
                ''
            ) AS supplier_name,

            COALESCE(
                sle.stock_uom,
                ''
            ) AS stock_uom,

            COALESCE(
                sle.stock_uom,
                ''
            ) AS uom_in_qty,

            COALESCE(
                SUM(sle.stock_value_difference),
                0
            ) AS stock_value,

            sle.company AS company,

            company.default_currency AS company_currency

        FROM `tabStock Ledger Entry` sle

        INNER JOIN `tabCompany` company
            ON company.name = sle.company

        INNER JOIN `tabItem` item
            ON item.name = sle.item_code

        LEFT JOIN `tabItem Variant Attribute` iva
            ON iva.parent = sle.item_code
            AND iva.parenttype = 'Item'
            AND iva.attribute = 'Brand'

        LEFT JOIN `tabPurchase Receipt` pr
            ON sle.voucher_type = 'Purchase Receipt'
            AND pr.name = sle.voucher_no

        LEFT JOIN `tabPurchase Receipt Item` pri
            ON sle.voucher_type = 'Purchase Receipt'
            AND pri.name = sle.voucher_detail_no

        LEFT JOIN `tabStock Entry` se
            ON sle.voucher_type = 'Stock Entry'
            AND se.name = sle.voucher_no

        LEFT JOIN `tabStock Entry Detail` sed
            ON sle.voucher_type = 'Stock Entry'
            AND sed.name = sle.voucher_detail_no

        LEFT JOIN `tabSupplier` supplier
            ON supplier.name = COALESCE(
                pr.supplier,
                se.supplier
            )

        WHERE
            {" AND ".join(conditions)}

        GROUP BY
            iva.attribute_value,
            COALESCE(
                item.variant_of,
                sle.item_code
            ),
            sle.item_code,
            item.item_name,
            COALESCE(
                pr.supplier,
                se.supplier
            ),
            COALESCE(
                pr.supplier_name,
                se.supplier_name
            ),
            sle.stock_uom,
            sle.company,
            company.default_currency

        ORDER BY
            COALESCE(
                iva.attribute_value,
                ''
            ),
            COALESCE(
                item.variant_of,
                sle.item_code
            ),
            COALESCE(
                pr.supplier_name,
                se.supplier_name,
                ''
            )
        """,
        filters,
        as_dict=True,
    )

    for row in rows:
        row.voucher = (
            "1 Voucher"
            if row.voucher_count == 1
            else f"{row.voucher_count} Vouchers"
        )

    return rows


def get_conditions(filters):
    conditions = [
        "sle.is_cancelled = 0",
        "sle.actual_qty > 0",
        "sle.voucher_type IN ('Purchase Receipt', 'Stock Entry')",
        "sle.company = %(company)s",
        "sle.posting_date BETWEEN %(from_date)s AND %(to_date)s",
        "COALESCE(pr.docstatus, se.docstatus) = 1",
    ]

    if filters.get("voucher_type"):
        conditions.append(
            "sle.voucher_type = %(voucher_type)s"
        )

    if filters.get("voucher_no"):
        conditions.append(
            "sle.voucher_no = %(voucher_no)s"
        )

    if filters.get("stock_entry_type"):
        conditions.append(
            "sle.voucher_type = 'Stock Entry'"
        )
        conditions.append(
            "se.stock_entry_type = %(stock_entry_type)s"
        )

    if filters.get("supplier"):
        conditions.append(
            "COALESCE(pr.supplier, se.supplier) = %(supplier)s"
        )

    if filters.get("supplier_group"):
        conditions.append(
            get_descendant_condition(
                "Supplier Group",
                "supplier.supplier_group",
                "supplier_group",
            )
        )

    if filters.get("supplier_delivery_note"):
        conditions.append(
            "pr.supplier_delivery_note = %(supplier_delivery_note)s"
        )

    if filters.get("item_code"):
        conditions.append(
            "sle.item_code = %(item_code)s"
        )

    if filters.get("item_group"):
        conditions.append(
            get_descendant_condition(
                "Item Group",
                "item.item_group",
                "item_group",
            )
        )

    if filters.get("brand"):
        conditions.append(
            "iva.attribute_value = %(brand)s"
        )

    if filters.get("warehouse"):
        conditions.append(
            get_descendant_condition(
                "Warehouse",
                "sle.warehouse",
                "warehouse",
            )
        )

    if filters.get("source_warehouse"):
        conditions.append(
            "COALESCE("
            "sed.s_warehouse, "
            "pri.from_warehouse"
            ") = %(source_warehouse)s"
        )

    if filters.get("purchase_order"):
        conditions.append(
            "pri.purchase_order = %(purchase_order)s"
        )

    if filters.get("project"):
        conditions.append(
            "COALESCE("
            "sed.project, "
            "pri.project, "
            "se.project, "
            "pr.project"
            ") = %(project)s"
        )

    if filters.get("batch_no"):
        conditions.append(
            "("
            "sle.batch_no = %(batch_no)s "
            "OR EXISTS ("
            "    SELECT 1 "
            "    FROM `tabSerial and Batch Entry` sbe "
            "    WHERE sbe.parent = sle.serial_and_batch_bundle "
            "    AND sbe.batch_no = %(batch_no)s"
            ")"
            ")"
        )

    return conditions


def get_report_summary(rows):
    if not rows:
        return []

    brands = {
        row.brand
        for row in rows
        if row.brand
    }

    stock_uoms = {
        row.stock_uom
        for row in rows
        if row.stock_uom
    }

    summary = [
        {
            "label": _("Consolidated Rows"),
            "value": len(rows),
            "datatype": "Int",
            "indicator": "Blue",
        },
        {
            "label": _("Brands"),
            "value": len(brands),
            "datatype": "Int",
            "indicator": "Blue",
        },
        {
            "label": _("Stock Value"),
            "value": sum(
                flt(row.stock_value)
                for row in rows
            ),
            "datatype": "Currency",
            "currency": rows[0].company_currency,
            "indicator": "Green",
        },
    ]

    if len(stock_uoms) == 1:
        uom = next(iter(stock_uoms))

        summary.insert(
            1,
            {
                "label": _("Inward Qty ({0})").format(uom),
                "value": sum(
                    flt(row.in_qty)
                    for row in rows
                ),
                "datatype": "Float",
                "indicator": "Green",
            },
        )

    return summary