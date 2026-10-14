# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate

from srv_erp.srv_erp.report.hierarchical_filters import get_descendant_condition
from srv_erp.srv_erp.report.uom_utils import add_selected_uom_columns


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)
	columns = get_columns()
	data = get_data(filters)
	add_selected_uom_columns(columns, data, filters.get("include_uom"))
	return columns, data


def validate_filters(filters):
	if not filters.get("company"):
		frappe.throw(_("Company is required."))
	if not filters.get("from_date") or not filters.get("to_date"):
		frappe.throw(_("From Date and To Date are required."))
	if getdate(filters.from_date) > getdate(filters.to_date):
		frappe.throw(_("From Date cannot be after To Date."))


def get_columns():
	return [
		{
			"label": _("Delivery Note"),
			"fieldname": "delivery_note",
			"fieldtype": "Link",
			"options": "Delivery Note",
			"width": 140,
		},
		{"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 140},
		{"label": _("Customer Name"), "fieldname": "customer_name", "fieldtype": "Data", "width": 180},
		{
			"label": _("Customer Group"),
			"fieldname": "customer_group",
			"fieldtype": "Link",
			"options": "Customer Group",
			"width": 130,
		},
		{"label": _("Territory"), "fieldname": "territory", "fieldtype": "Link", "options": "Territory", "width": 120},
		{"label": _("Sales Person"), "fieldname": "sales_person", "fieldtype": "Data", "width": 150},
		{"label": _("Item Code"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 140},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 180},
		{
			"label": _("Item Group"),
			"fieldname": "item_group",
			"fieldtype": "Link",
			"options": "Item Group",
			"width": 130,
		},
		{"label": _("Brand"), "fieldname": "brand", "fieldtype": "Link", "options": "Brand", "width": 120},
		{
			"label": _("Delivered Qty"),
			"fieldname": "qty",
			"fieldtype": "Float",
			"width": 110,
			"convertible": "qty",
		},
		{"label": _("UOM"), "fieldname": "uom_qty", "fieldtype": "Link", "options": "UOM", "width": 90},
		{"label": _("Stock Qty"), "fieldname": "stock_qty", "fieldtype": "Float", "width": 110},
		{"label": _("Stock UOM"), "fieldname": "stock_uom", "fieldtype": "Link", "options": "UOM", "width": 100},
		{
			"label": _("Warehouse"),
			"fieldname": "warehouse",
			"fieldtype": "Link",
			"options": "Warehouse",
			"width": 140,
		},
		{"label": _("Sales Order"), "fieldname": "sales_order", "fieldtype": "Link", "options": "Sales Order", "width": 140},
		{"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 120},
		{"label": _("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 120},
	]


def get_data(filters):
	return frappe.db.sql(
		f"""
			SELECT
				dn.name AS delivery_note,
				dn.posting_date,
				dn.customer,
				dn.customer_name,
				dn.customer_group,
				dn.territory,
				(
					SELECT GROUP_CONCAT(DISTINCT st.sales_person ORDER BY st.idx SEPARATOR ', ')
					FROM `tabSales Team` st
					WHERE st.parent = dn.name AND st.parenttype = 'Delivery Note'
				) AS sales_person,
				dni.item_code,
				dni.item_name,
				dni.item_group,
				dni.brand,
				dni.qty,
				dni.uom AS uom_qty,
				dni.stock_qty,
				dni.stock_uom,
				dni.warehouse,
				dni.against_sales_order AS sales_order,
				dn.project,
				dn.company
			FROM `tabDelivery Note Item` dni
			INNER JOIN `tabDelivery Note` dn ON dn.name = dni.parent
			WHERE
				dn.docstatus = 1
				AND COALESCE(dn.is_return, 0) = 0
				AND dni.qty > 0
				{get_conditions(filters)}
			ORDER BY dn.posting_date DESC, dn.name DESC, dni.idx
		""",
		filters,
		as_dict=True,
	)


def get_conditions(filters):
	conditions = []
	field_map = {
		"company": "dn.company",
		"customer": "dn.customer",
		"territory": "dn.territory",
		"project": "dn.project",
		"item_code": "dni.item_code",
		"brand": "dni.brand",
		"sales_order": "dni.against_sales_order",
		"warehouse": "dni.warehouse",
	}

	if filters.get("from_date"):
		conditions.append("dn.posting_date >= %(from_date)s")
	if filters.get("to_date"):
		conditions.append("dn.posting_date <= %(to_date)s")
	for fieldname, column in field_map.items():
		if filters.get(fieldname):
			conditions.append(f"{column} = %({fieldname})s")
	if filters.get("customer_group"):
		conditions.append(
			get_descendant_condition("Customer Group", "dn.customer_group", "customer_group")
		)
	if filters.get("item_group"):
		conditions.append(
			get_descendant_condition("Item Group", "dni.item_group", "item_group")
		)
	if filters.get("sales_person"):
		conditions.append(
			"EXISTS ("
			"SELECT 1 FROM `tabSales Team` st_filter "
			"WHERE st_filter.parent = dn.name "
			"AND st_filter.parenttype = 'Delivery Note' "
			"AND st_filter.sales_person = %(sales_person)s)"
		)

	return " AND " + " AND ".join(conditions) if conditions else ""
