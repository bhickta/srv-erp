# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Item Code"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 120},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 160},
		{"label": _("Item Group"), "fieldname": "item_group", "fieldtype": "Link", "options": "Item Group", "width": 120},
		{"label": _("Brand"), "fieldname": "brand", "fieldtype": "Link", "options": "Brand", "width": 120},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 140},
		{"label": _("Customer Name"), "fieldname": "customer_name", "fieldtype": "Data", "width": 160},
		{"label": _("Customer Group"), "fieldname": "customer_group", "fieldtype": "Link", "options": "Customer Group", "width": 130},
		{"label": _("Territory"), "fieldname": "territory", "fieldtype": "Link", "options": "Territory", "width": 120},
		{"label": _("Sales Person"), "fieldname": "sales_person", "fieldtype": "Data", "width": 140},
		{"label": _("Order Date"), "fieldname": "transaction_date", "fieldtype": "Date", "width": 100},
		{"label": _("Delivery Date"), "fieldname": "delivery_date", "fieldtype": "Date", "width": 100},
		{"label": _("UOM"), "fieldname": "uom", "fieldtype": "Link", "options": "UOM", "width": 90},
		{"label": _("Qty Ordered"), "fieldname": "qty", "fieldtype": "Float", "width": 105},
		{"label": _("Stock UOM"), "fieldname": "stock_uom", "fieldtype": "Link", "options": "UOM", "width": 90},
		{"label": _("Stock Qty Ordered"), "fieldname": "stock_qty", "fieldtype": "Float", "width": 125},
		{"label": _("Stock Qty Delivered"), "fieldname": "delivered_qty", "fieldtype": "Float", "width": 130},
		{"label": _("Stock Qty Pending"), "fieldname": "pending_qty", "fieldtype": "Float", "width": 120},
		{"label": _("Rate"), "fieldname": "rate", "fieldtype": "Currency", "options": "Company:company:default_currency", "width": 100},
		{"label": _("Amount (Net)"), "fieldname": "amount", "fieldtype": "Currency", "options": "Company:company:default_currency", "width": 120},
		{"label": _("Sales Order"), "fieldname": "sales_order", "fieldtype": "Link", "options": "Sales Order", "width": 130},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
		{"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 120},
		{"label": _("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 120},
	]


def get_data(filters):
	conditions = get_conditions(filters)
	return frappe.db.sql(
		f"""
			SELECT
				soi.item_code,
				soi.item_name,
				soi.item_group,
				soi.brand,
				so.customer,
				so.customer_name,
				so.customer_group,
				so.territory,
				(
					SELECT GROUP_CONCAT(DISTINCT st.sales_person ORDER BY st.idx SEPARATOR ', ')
					FROM `tabSales Team` st
					WHERE st.parent = so.name AND st.parenttype = 'Sales Order'
				) AS sales_person,
				so.transaction_date,
				soi.delivery_date,
				soi.uom,
				soi.qty,
				soi.stock_uom,
				soi.stock_qty,
				soi.delivered_qty,
				GREATEST(soi.stock_qty - soi.delivered_qty, 0) AS pending_qty,
				soi.base_net_rate AS rate,
				soi.base_net_amount AS amount,
				so.name AS sales_order,
				so.status,
				so.project,
				so.company
			FROM `tabSales Order Item` soi
			INNER JOIN `tabSales Order` so ON so.name = soi.parent
			WHERE so.docstatus = 1 {conditions}
			ORDER BY soi.item_code, so.transaction_date DESC, so.name, soi.idx
		""",
		filters,
		as_dict=True,
	)


def get_conditions(filters):
	conditions = []
	field_map = {
		"company": "so.company",
		"customer": "so.customer",
		"customer_group": "so.customer_group",
		"territory": "so.territory",
		"project": "so.project",
		"item_code": "soi.item_code",
		"item_group": "soi.item_group",
		"brand": "soi.brand",
	}

	if filters.get("from_date"):
		conditions.append("so.transaction_date >= %(from_date)s")
	if filters.get("to_date"):
		conditions.append("so.transaction_date <= %(to_date)s")
	for fieldname, column in field_map.items():
		if filters.get(fieldname):
			conditions.append(f"{column} = %({fieldname})s")
	if filters.get("sales_person"):
		conditions.append(
			"EXISTS (SELECT 1 FROM `tabSales Team` st_filter "
			"WHERE st_filter.parent = so.name AND st_filter.parenttype = 'Sales Order' "
			"AND st_filter.sales_person = %(sales_person)s)"
		)

	return " AND " + " AND ".join(conditions) if conditions else ""
