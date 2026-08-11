# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate
from dateutil.relativedelta import relativedelta

from srv_erp.srv_erp.report.hierarchical_filters import get_descendant_condition
from srv_erp.srv_erp.report.uom_utils import add_selected_uom_columns


def execute(filters=None):
	filters = frappe._dict(filters or {})
	set_default_warehouse(filters)
	validate_warehouse(filters)
	columns = get_columns()
	data = get_data(filters)
	add_selected_uom_columns(columns, data, filters.get("include_uom"))
	return columns, data

def get_columns():
	return [
		{
			"label": _("Item Code"),
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "Item",
			"width": 120,
		},
		{
			"label": _("Item Name"),
			"fieldname": "item_name",
			"fieldtype": "Data",
			"width": 160,
		},
		{
			"label": _("Item Group"),
			"fieldname": "item_group",
			"fieldtype": "Link",
			"options": "Item Group",
			"width": 120,
		},
		{
			"label": _("Brand"),
			"fieldname": "brand",
			"fieldtype": "Link",
			"options": "Brand",
			"width": 120,
		},
		{
			"label": _("Customer"),
			"fieldname": "customer",
			"fieldtype": "Link",
			"options": "Customer",
			"width": 140,
		},
		{
			"label": _("Customer Name"),
			"fieldname": "customer_name",
			"fieldtype": "Data",
			"width": 160,
		},
		{
			"label": _("Customer Group"),
			"fieldname": "customer_group",
			"fieldtype": "Link",
			"options": "Customer Group",
			"width": 130,
		},
		{
			"label": _("Territory"),
			"fieldname": "territory",
			"fieldtype": "Link",
			"options": "Territory",
			"width": 120,
		},
		{
			"label": _("Sales Person"),
			"fieldname": "sales_person",
			"fieldtype": "Data",
			"width": 140,
		},
		{
			"label": _("Posting Date"),
			"fieldname": "posting_date",
			"fieldtype": "Date",
			"width": 100,
		},
		{
			"label": _("Qty Delivered"),
			"fieldname": "qty",
			"fieldtype": "Float",
			"width": 100,
		},
		{
			"label": _("Qty Delivered UOM"),
			"fieldname": "uom_qty",
			"fieldtype": "Link",
			"options": "UOM",
			"width": 115,
		},
		{
			"label": _("Stock Available"),
			"fieldname": "stock_available_qty",
			"fieldtype": "Float",
			"width": 115,
			"convertible": "qty",
		},
		{
			"label": _("Stock Available UOM"),
			"fieldname": "uom_stock_available_qty",
			"fieldtype": "Link",
			"options": "UOM",
			"width": 125,
		},
		{
			"label": _("Stock Qty Delivered"),
			"fieldname": "stock_qty",
			"fieldtype": "Float",
			"width": 130,
			"convertible": "qty",
		},
		{
			"label": _("Stock Qty Delivered UOM"),
			"fieldname": "uom_stock_qty",
			"fieldtype": "Link",
			"options": "UOM",
			"width": 130,
		},
		{
			"label": _("Difference (Stock - Delivered)"),
			"fieldname": "difference_qty",
			"fieldtype": "Float",
			"width": 160,
		},
		{
			"label": _("Difference Stock UOM"),
			"fieldname": "uom_difference_qty",
			"fieldtype": "Link",
			"options": "UOM",
			"width": 110,
		},
		{
			"label": _("Delivery Note"),
			"fieldname": "delivery_note",
			"fieldtype": "Link",
			"options": "Delivery Note",
			"width": 130,
		},
		{
			"label": _("Project"),
			"fieldname": "project",
			"fieldtype": "Link",
			"options": "Project",
			"width": 120,
		},
		{
			"label": _("Company"),
			"fieldname": "company",
			"fieldtype": "Link",
			"options": "Company",
			"width": 120,
		},
	]


def get_data(filters):
	conditions = get_conditions(filters)
	
	data = frappe.db.sql(f"""
		SELECT
			dni.item_code,
			dni.item_name,
			dni.item_group,
			dni.brand,
			dni.uom AS uom_qty,
			dn.customer,
			dn.customer_name,
			dn.customer_group,
			dn.territory,
			dn.project,
			(SELECT GROUP_CONCAT(sales_person SEPARATOR ', ') FROM `tabSales Team` WHERE parent = dn.name) as sales_person,
			dn.posting_date,
			dni.qty,
			COALESCE(bin.actual_qty, 0) AS stock_available_qty,
			item.stock_uom AS uom_stock_available_qty,
			dni.stock_uom AS uom_stock_qty,
			dni.stock_qty,
			COALESCE(bin.actual_qty, 0) - dni.stock_qty AS difference_qty,
			item.stock_uom AS uom_difference_qty,
			dn.name as delivery_note,
			dn.company
		FROM
			`tabDelivery Note Item` dni
		INNER JOIN
			`tabDelivery Note` dn ON dni.parent = dn.name
		INNER JOIN
			`tabItem` item ON item.name = dni.item_code
		LEFT JOIN
			`tabBin` bin ON bin.item_code = dni.item_code AND bin.warehouse = %(warehouse)s
		WHERE
			dn.docstatus = 1
			{conditions}
		ORDER BY
			dn.posting_date desc
	""", filters, as_dict=1)

	return data

def get_conditions(filters):
	conditions = ""
	if filters.get("from_date"):
		conditions += " AND dn.posting_date >= %(from_date)s"
	if filters.get("to_date"):
		conditions += " AND dn.posting_date <= %(to_date)s"
	if filters.get("company"):
		conditions += " AND dn.company = %(company)s"
	if filters.get("customer"):
		conditions += " AND dn.customer = %(customer)s"
	if filters.get("customer_group"):
		conditions += " AND " + get_descendant_condition(
			"Customer Group", "dn.customer_group", "customer_group"
		)
	if filters.get("territory"):
		conditions += " AND dn.territory = %(territory)s"
	if filters.get("project"):
		conditions += " AND dn.project = %(project)s"
	if filters.get("item_code"):
		conditions += " AND dni.item_code = %(item_code)s"
	if filters.get("item_group"):
		conditions += " AND " + get_descendant_condition("Item Group", "dni.item_group", "item_group")
	if filters.get("brand"):
		conditions += " AND dni.brand = %(brand)s"
	if filters.get("sales_person"):
		conditions += " AND EXISTS (SELECT name FROM `tabSales Team` WHERE parent = dn.name AND sales_person = %(sales_person)s)"
	return conditions


def set_default_warehouse(filters):
	if filters.get("warehouse") or not filters.get("company"):
		return

	filters["warehouse"] = frappe.db.get_value(
		"Warehouse",
		{
			"company": filters.company,
			"warehouse_name": "Finished Goods",
			"is_group": 0,
			"disabled": 0,
		},
		"name",
	)


def validate_warehouse(filters):
	if not filters.get("warehouse"):
		frappe.throw(
			_("Please select a Warehouse. No enabled Finished Goods warehouse was found for {0}.").format(
				filters.company
			)
		)

	warehouse = frappe.db.get_value(
		"Warehouse",
		filters.warehouse,
		["company", "is_group", "disabled"],
		as_dict=True,
	)
	if not warehouse or warehouse.disabled or warehouse.is_group:
		frappe.throw(_("Please select an enabled, non-group Warehouse."))
	if warehouse.company != filters.company:
		frappe.throw(_("Warehouse {0} does not belong to company {1}.").format(filters.warehouse, filters.company))
