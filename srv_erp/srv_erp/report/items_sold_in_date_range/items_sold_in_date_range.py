# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate
from dateutil.relativedelta import relativedelta


def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{
			"label": _("Period"),
			"fieldname": "period",
			"fieldtype": "Data",
			"width": 120,
		},
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
			"label": _("UOM"),
			"fieldname": "uom",
			"fieldtype": "Link",
			"options": "UOM",
			"width": 90,
		},
		{
			"label": _("Qty Sold"),
			"fieldname": "qty",
			"fieldtype": "Float",
			"width": 100,
		},
		{
			"label": _("Rate"),
			"fieldname": "rate",
			"fieldtype": "Currency",
			"options": "Company:company:default_currency",
			"width": 100,
		},
		{
			"label": _("Discount Amount"),
			"fieldname": "discount_amount",
			"fieldtype": "Currency",
			"options": "Company:company:default_currency",
			"width": 120,
		},
		{
			"label": _("Amount (Net)"),
			"fieldname": "amount",
			"fieldtype": "Currency",
			"options": "Company:company:default_currency",
			"width": 120,
		},
		{
			"label": _("Sales Invoice"),
			"fieldname": "sales_invoice",
			"fieldtype": "Link",
			"options": "Sales Invoice",
			"width": 130,
		},
		{
			"label": _("Sales Order"),
			"fieldname": "sales_order",
			"fieldtype": "Link",
			"options": "Sales Order",
			"width": 120,
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
	
	# Fetch sales invoice items with joined invoice details
	data = frappe.db.sql(f"""
		SELECT
			sii.item_code,
			sii.item_name,
			sii.item_group,
			sii.brand,
			sii.uom,
			si.customer,
			si.customer_name,
			si.customer_group,
			si.territory,
			si.project,
			(SELECT GROUP_CONCAT(sales_person SEPARATOR ', ') FROM `tabSales Team` WHERE parent = si.name) as sales_person,
			si.posting_date,
			sii.qty,
			sii.base_rate as rate,
			(sii.base_rate * sii.qty - sii.base_net_amount) as discount_amount,
			sii.base_net_amount as amount,
			si.name as sales_invoice,
			sii.sales_order,
			si.company
		FROM
			`tabSales Invoice Item` sii
		INNER JOIN
			`tabSales Invoice` si ON sii.parent = si.name
		WHERE
			si.docstatus = 1
			{conditions}
		ORDER BY
			si.posting_date desc
	""", filters, as_dict=1)

	range_filter = filters.get("range", "Daily")
	
	for row in data:
		posting_date = getdate(row.posting_date)
		if range_filter == "Daily":
			row.period = posting_date.strftime("%Y-%m-%d")
		elif range_filter == "Weekly":
			# Get week start (Monday)
			start = posting_date - relativedelta(days=posting_date.weekday())
			end = start + relativedelta(days=6)
			row.period = f"{start.strftime('%d-%b-%Y')} to {end.strftime('%d-%b-%Y')}"
		elif range_filter == "Monthly":
			row.period = posting_date.strftime("%b %Y")
		elif range_filter == "Quarterly":
			quarter = (posting_date.month - 1) // 3 + 1
			row.period = f"Q{quarter} {posting_date.year}"
		elif range_filter == "Yearly":
			row.period = str(posting_date.year)

	return data

def get_conditions(filters):
	conditions = ""
	if filters.get("from_date"):
		conditions += " AND si.posting_date >= %(from_date)s"
	if filters.get("to_date"):
		conditions += " AND si.posting_date <= %(to_date)s"
	if filters.get("company"):
		conditions += " AND si.company = %(company)s"
	if filters.get("customer"):
		conditions += " AND si.customer = %(customer)s"
	if filters.get("customer_group"):
		conditions += " AND si.customer_group = %(customer_group)s"
	if filters.get("territory"):
		conditions += " AND si.territory = %(territory)s"
	if filters.get("project"):
		conditions += " AND si.project = %(project)s"
	if filters.get("item_code"):
		conditions += " AND sii.item_code = %(item_code)s"
	if filters.get("item_group"):
		conditions += " AND sii.item_group = %(item_group)s"
	if filters.get("brand"):
		conditions += " AND sii.brand = %(brand)s"
	if filters.get("sales_person"):
		conditions += " AND EXISTS (SELECT name FROM `tabSales Team` WHERE parent = si.name AND sales_person = %(sales_person)s)"
	return conditions
