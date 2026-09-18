# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from itertools import groupby

import frappe
from frappe import _
from frappe.utils import flt, getdate

from srv_erp.srv_erp.report.hierarchical_filters import get_descendant_condition

INWARD_VOUCHER_TYPES = ("Purchase Receipt", "Stock Entry")

GROUP_BY = {
	"Voucher": ("voucher_group", "Voucher", ("sle.voucher_type", "sle.voucher_no")),
	"Voucher Type": ("voucher_type", "Voucher Type", ("sle.voucher_type",)),
	"Supplier": ("supplier", "Supplier", ("supplier.supplier_name", "supplier.name")),
	"Supplier Group": ("supplier_group", "Supplier Group", ("supplier.supplier_group",)),
	"Item": ("item_code", "Item", ("item.item_name", "sle.item_code")),
	"Item Group": ("item_group", "Item Group", ("item.item_group",)),
	"Warehouse": ("warehouse", "Warehouse", ("sle.warehouse",)),
	"Posting Date": ("posting_date", "Posting Date", ("sle.posting_date",)),
	"Stock Entry Type": ("inward_type", "Stock Entry Type", ("inward_type",)),
}

SORT_BY = {
	"Posting Date": ("sle.posting_date", "sle.posting_time"),
	"Voucher": ("sle.voucher_type", "sle.voucher_no"),
	"Supplier": ("supplier.supplier_name", "supplier.name"),
	"Item": ("item.item_name", "sle.item_code"),
	"Item Group": ("item.item_group", "item.item_name"),
	"Warehouse": ("sle.warehouse", "item.item_name"),
	"Quantity": ("sle.actual_qty",),
	"Stock Value": ("sle.stock_value_difference",),
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)

	columns = get_columns(filters)
	rows = get_data(filters)
	set_batch_numbers(rows)
	report_summary = get_report_summary(rows)
	data = add_group_rows(rows, filters.get("group_by"))

	return columns, data, None, None, report_summary, True


def validate_filters(filters):
	if not filters.get("company"):
		frappe.throw(_("Company is required."))
	if not filters.get("from_date") or not filters.get("to_date"):
		frappe.throw(_("From Date and To Date are required."))
	if getdate(filters.from_date) > getdate(filters.to_date):
		frappe.throw(_("From Date cannot be after To Date."))
	if filters.get("voucher_type") and filters.voucher_type not in INWARD_VOUCHER_TYPES:
		frappe.throw(_("Voucher Type must be Purchase Receipt or Stock Entry."))
	if filters.get("voucher_no") and not filters.get("voucher_type"):
		frappe.throw(_("Please select a Voucher Type before selecting a Voucher."))
	if filters.get("group_by") and filters.group_by not in GROUP_BY:
		frappe.throw(_("Invalid Group By option."))
	if filters.get("sort_by") and filters.sort_by not in SORT_BY:
		frappe.throw(_("Invalid Sort By option."))
	if filters.get("sort_order") and filters.sort_order not in ("Ascending", "Descending"):
		frappe.throw(_("Invalid Sort Order option."))


def get_columns(filters):
	columns = []
	if filters.get("group_by"):
		columns.append(
			{
				"label": _(GROUP_BY[filters.group_by][1]),
				"fieldname": "group_label",
				"fieldtype": "Data",
				"width": 220,
			}
		)

	columns.extend(
		[
			{"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
			{"label": _("Posting Time"), "fieldname": "posting_time", "fieldtype": "Time", "width": 90},
			{"label": _("Voucher Type"), "fieldname": "voucher_type", "fieldtype": "Data", "width": 130},
			{
				"label": _("Voucher"),
				"fieldname": "voucher_no",
				"fieldtype": "Dynamic Link",
				"options": "voucher_type",
				"width": 150,
			},
			{"label": _("Stock Entry Type"), "fieldname": "inward_type", "fieldtype": "Data", "width": 140},
			{
				"label": _("Supplier"),
				"fieldname": "supplier",
				"fieldtype": "Link",
				"options": "Supplier",
				"width": 130,
			},
			{"label": _("Supplier Name"), "fieldname": "supplier_name", "fieldtype": "Data", "width": 170},
			{
				"label": _("Supplier Group"),
				"fieldname": "supplier_group",
				"fieldtype": "Link",
				"options": "Supplier Group",
				"width": 130,
			},
			{
				"label": _("Supplier Delivery Note"),
				"fieldname": "supplier_delivery_note",
				"fieldtype": "Data",
				"width": 160,
			},
			{
				"label": _("Item"),
				"fieldname": "item_code",
				"fieldtype": "Link",
				"options": "Item",
				"width": 140,
			},
			{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 180},
			{
				"label": _("Item Group"),
				"fieldname": "item_group",
				"fieldtype": "Link",
				"options": "Item Group",
				"width": 130,
			},
			{
				"label": _("Brand"),
				"fieldname": "brand",
				"fieldtype": "Link",
				"options": "Brand",
				"width": 100,
			},
			{
				"label": _("Inward Qty"),
				"fieldname": "in_qty",
				"fieldtype": "Float",
				"width": 110,
			},
			{
				"label": _("Stock UOM"),
				"fieldname": "stock_uom",
				"fieldtype": "Link",
				"options": "UOM",
				"width": 90,
			},
			{
				"label": _("Incoming Rate"),
				"fieldname": "incoming_rate",
				"fieldtype": "Currency",
				"options": "company_currency",
				"width": 115,
			},
			{
				"label": _("Stock Value"),
				"fieldname": "stock_value",
				"fieldtype": "Currency",
				"options": "company_currency",
				"width": 120,
			},
			{
				"label": _("Target Warehouse"),
				"fieldname": "warehouse",
				"fieldtype": "Link",
				"options": "Warehouse",
				"width": 160,
			},
			{
				"label": _("Source Warehouse"),
				"fieldname": "source_warehouse",
				"fieldtype": "Link",
				"options": "Warehouse",
				"width": 160,
			},
			{"label": _("Batch"), "fieldname": "batch_no", "fieldtype": "Data", "width": 140},
			{
				"label": _("Serial and Batch Bundle"),
				"fieldname": "serial_and_batch_bundle",
				"fieldtype": "Link",
				"options": "Serial and Batch Bundle",
				"width": 170,
			},
			{
				"label": _("Purchase Order"),
				"fieldname": "purchase_order",
				"fieldtype": "Link",
				"options": "Purchase Order",
				"width": 140,
			},
			{
				"label": _("Project"),
				"fieldname": "project",
				"fieldtype": "Link",
				"options": "Project",
				"width": 120,
			},
			{
				"label": _("Cost Center"),
				"fieldname": "cost_center",
				"fieldtype": "Link",
				"options": "Cost Center",
				"width": 130,
			},
			{
				"label": _("Item Remarks"),
				"fieldname": "item_remarks",
				"fieldtype": "Small Text",
				"width": 180,
			},
			{
				"label": _("Voucher Remarks"),
				"fieldname": "voucher_remarks",
				"fieldtype": "Small Text",
				"width": 180,
			},
			{
				"label": _("Company"),
				"fieldname": "company",
				"fieldtype": "Link",
				"options": "Company",
				"width": 130,
			},
			{
				"label": _("Currency"),
				"fieldname": "company_currency",
				"fieldtype": "Link",
				"options": "Currency",
				"hidden": 1,
			},
		]
	)
	return columns


def get_data(filters):
	conditions = get_conditions(filters)
	order_by = get_order_by(filters)

	rows = frappe.db.sql(
		f"""
			SELECT
				sle.posting_date,
				sle.posting_time,
				sle.voucher_type,
				sle.voucher_no,
				CASE
					WHEN sle.voucher_type = 'Stock Entry' THEN se.stock_entry_type
					ELSE 'Purchase Receipt'
				END AS inward_type,
				COALESCE(pr.supplier, se.supplier) AS supplier,
				COALESCE(pr.supplier_name, se.supplier_name) AS supplier_name,
				supplier.supplier_group,
				pr.supplier_delivery_note,
				sle.item_code,
				item.item_name,
				item.item_group,
				item.brand,
				sle.actual_qty AS in_qty,
				sle.stock_uom,
				sle.incoming_rate,
				sle.stock_value_difference AS stock_value,
				sle.warehouse,
				COALESCE(sed.s_warehouse, pri.from_warehouse) AS source_warehouse,
				sle.batch_no,
				sle.serial_and_batch_bundle,
				pri.purchase_order,
				COALESCE(sed.project, pri.project, se.project, pr.project) AS project,
				COALESCE(sed.cost_center, pri.cost_center) AS cost_center,
				COALESCE(sed.description, pri.description) AS item_remarks,
				COALESCE(se.remarks, pr.remarks) AS voucher_remarks,
				sle.company,
				company.default_currency AS company_currency
			FROM `tabStock Ledger Entry` sle
			INNER JOIN `tabCompany` company ON company.name = sle.company
			INNER JOIN `tabItem` item ON item.name = sle.item_code
			LEFT JOIN `tabPurchase Receipt` pr
				ON sle.voucher_type = 'Purchase Receipt' AND pr.name = sle.voucher_no
			LEFT JOIN `tabPurchase Receipt Item` pri
				ON sle.voucher_type = 'Purchase Receipt' AND pri.name = sle.voucher_detail_no
			LEFT JOIN `tabStock Entry` se
				ON sle.voucher_type = 'Stock Entry' AND se.name = sle.voucher_no
			LEFT JOIN `tabStock Entry Detail` sed
				ON sle.voucher_type = 'Stock Entry' AND sed.name = sle.voucher_detail_no
			LEFT JOIN `tabSupplier` supplier ON supplier.name = COALESCE(pr.supplier, se.supplier)
			WHERE {" AND ".join(conditions)}
			ORDER BY {order_by}, sle.name {get_sort_direction(filters)}
		""",
		filters,
		as_dict=True,
	)

	for row in rows:
		row["voucher_group"] = f"{row.voucher_type}: {row.voucher_no}"
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
		conditions.append("sle.voucher_type = %(voucher_type)s")
	if filters.get("voucher_no"):
		conditions.append("sle.voucher_no = %(voucher_no)s")
	if filters.get("stock_entry_type"):
		conditions.append("sle.voucher_type = 'Stock Entry'")
		conditions.append("se.stock_entry_type = %(stock_entry_type)s")
	if filters.get("supplier"):
		conditions.append("COALESCE(pr.supplier, se.supplier) = %(supplier)s")
	if filters.get("supplier_group"):
		conditions.append(
			get_descendant_condition("Supplier Group", "supplier.supplier_group", "supplier_group")
		)
	if filters.get("supplier_delivery_note"):
		conditions.append("pr.supplier_delivery_note = %(supplier_delivery_note)s")
	if filters.get("item_code"):
		conditions.append("sle.item_code = %(item_code)s")
	if filters.get("item_group"):
		conditions.append(get_descendant_condition("Item Group", "item.item_group", "item_group"))
	if filters.get("brand"):
		conditions.append("item.brand = %(brand)s")
	if filters.get("warehouse"):
		conditions.append(get_descendant_condition("Warehouse", "sle.warehouse", "warehouse"))
	if filters.get("source_warehouse"):
		conditions.append("COALESCE(sed.s_warehouse, pri.from_warehouse) = %(source_warehouse)s")
	if filters.get("purchase_order"):
		conditions.append("pri.purchase_order = %(purchase_order)s")
	if filters.get("project"):
		conditions.append("COALESCE(sed.project, pri.project, se.project, pr.project) = %(project)s")
	if filters.get("batch_no"):
		conditions.append(
			"(sle.batch_no = %(batch_no)s OR EXISTS ("
			"SELECT 1 FROM `tabSerial and Batch Entry` sbe "
			"WHERE sbe.parent = sle.serial_and_batch_bundle AND sbe.batch_no = %(batch_no)s"
			"))"
		)

	return conditions


def set_batch_numbers(rows):
	"""Populate batches stored in v15 Serial and Batch Bundles without splitting SLE quantities."""
	bundles = {row.serial_and_batch_bundle for row in rows if row.serial_and_batch_bundle}
	if not bundles:
		return

	batch_numbers = {}
	for entry in frappe.get_all(
		"Serial and Batch Entry",
		filters={"parent": ("in", sorted(bundles)), "batch_no": ("is", "set")},
		fields=["parent", "batch_no"],
		order_by="parent, idx",
	):
		batch_numbers.setdefault(entry.parent, [])
		if entry.batch_no not in batch_numbers[entry.parent]:
			batch_numbers[entry.parent].append(entry.batch_no)

	for row in rows:
		if not row.batch_no and row.serial_and_batch_bundle:
			row.batch_no = ", ".join(batch_numbers.get(row.serial_and_batch_bundle, []))


def get_order_by(filters):
	direction = get_sort_direction(filters)
	fields = []
	if filters.get("group_by"):
		fields.extend(GROUP_BY[filters.group_by][2])
	fields.extend(SORT_BY.get(filters.get("sort_by") or "Posting Date"))

	deduplicated_fields = list(dict.fromkeys(fields))
	return f" {direction}, ".join(deduplicated_fields) + f" {direction}"


def get_sort_direction(filters):
	return "ASC" if filters.get("sort_order") == "Ascending" else "DESC"


def add_group_rows(rows, group_by_option):
	if not group_by_option:
		return rows

	fieldname = GROUP_BY[group_by_option][0]
	grouped_rows = []
	for group_value, entries in groupby(rows, key=lambda row: row.get(fieldname)):
		entries = list(entries)
		stock_uoms = {row.stock_uom for row in entries if row.stock_uom}
		group_label = group_value or _("Not Set")
		if len(stock_uoms) != 1:
			group_label = _("{0} (Mixed UOM)").format(group_label)
		grouped_rows.append(
			frappe._dict(
				{
					"group_label": group_label,
					"in_qty": sum(flt(row.in_qty) for row in entries) if len(stock_uoms) == 1 else None,
					"stock_uom": next(iter(stock_uoms)) if len(stock_uoms) == 1 else None,
					"stock_value": sum(flt(row.stock_value) for row in entries),
					"company_currency": entries[0].company_currency,
					"is_group": 1,
					"indent": 0,
				}
			)
		)
		for row in entries:
			row["indent"] = 1
			grouped_rows.append(row)

	return grouped_rows


def get_report_summary(rows):
	if not rows:
		return []

	stock_uoms = {row.stock_uom for row in rows if row.stock_uom}
	summary = [
		{
			"label": _("Inward Rows"),
			"value": len(rows),
			"datatype": "Int",
			"indicator": "Blue",
		},
		{
			"label": _("Vouchers"),
			"value": len({(row.voucher_type, row.voucher_no) for row in rows}),
			"datatype": "Int",
			"indicator": "Blue",
		},
		{
			"label": _("Stock Value"),
			"value": sum(flt(row.stock_value) for row in rows),
			"datatype": "Currency",
			"currency": rows[0].company_currency,
			"indicator": "Green",
		},
	]
	if len(stock_uoms) == 1:
		uom = next(iter(stock_uoms))
		summary.insert(
			2,
			{
				"label": _("Inward Qty ({0})").format(uom),
				"value": sum(flt(row.in_qty) for row in rows),
				"datatype": "Float",
				"indicator": "Green",
			},
		)
	return summary
