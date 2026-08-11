# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import cint

from srv_erp.srv_erp.report.hierarchical_filters import get_descendant_condition
from srv_erp.srv_erp.report.uom_utils import add_selected_uom_columns


DEFAULT_BRAND_VARIANT_ATTRIBUTE = "Brand"
RESOLVED_BRAND_SQL = "COALESCE(NULLIF(variant_brand.attribute_value, ''), NULLIF(item.brand, ''), template.brand)"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	group_by_item = cint(filters.get("group_by_item", 1))
	columns = get_columns(group_by_item)
	data = get_data(filters, group_by_item)
	add_selected_uom_columns(columns, data, filters.get("include_uom"))
	return columns, data


def get_columns(group_by_item=False):
	if group_by_item:
		return get_grouped_columns()

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
		{"label": _("Qty Ordered"), "fieldname": "qty", "fieldtype": "Float", "width": 105},
		{"label": _("UOM"), "fieldname": "uom", "fieldtype": "Link", "options": "UOM", "width": 90},
		{"label": _("Stock Qty Ordered"), "fieldname": "stock_qty", "fieldtype": "Float", "width": 125, "convertible": "qty"},
		{"label": _("Stock UOM"), "fieldname": "stock_uom", "fieldtype": "Link", "options": "UOM", "width": 90},
		{"label": _("Stock Qty Delivered"), "fieldname": "delivered_qty", "fieldtype": "Float", "width": 130, "convertible": "qty"},
		{"label": _("Stock Qty Pending"), "fieldname": "pending_qty", "fieldtype": "Float", "width": 120, "convertible": "qty"},
		{"label": _("Sales Order"), "fieldname": "sales_order", "fieldtype": "Link", "options": "Sales Order", "width": 130},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
		{"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 120},
		{"label": _("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 120},
	]


def get_grouped_columns():
	return [
		{"label": _("Brand"), "fieldname": "brand", "fieldtype": "Link", "options": "Brand", "width": 120},
		{"label": _("Item Code"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 120},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 180},
		{"label": _("Item Group"), "fieldname": "item_group", "fieldtype": "Link", "options": "Item Group", "width": 120},
		{"label": _("Qty Ordered"), "fieldname": "qty", "fieldtype": "Float", "width": 105},
		{"label": _("UOM"), "fieldname": "uom", "fieldtype": "Link", "options": "UOM", "width": 90},
		{"label": _("Stock Qty Ordered"), "fieldname": "stock_qty", "fieldtype": "Float", "width": 125, "convertible": "qty"},
		{"label": _("Stock UOM"), "fieldname": "stock_uom", "fieldtype": "Link", "options": "UOM", "width": 90},
		{"label": _("Stock Qty Delivered"), "fieldname": "delivered_qty", "fieldtype": "Float", "width": 130, "convertible": "qty"},
		{"label": _("Stock Qty Pending"), "fieldname": "pending_qty", "fieldtype": "Float", "width": 120, "convertible": "qty"},
		{"label": _("Order Count"), "fieldname": "order_count", "fieldtype": "Int", "width": 95},
		{"label": _("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 120},
	]


def get_data(filters, group_by_item=False):
	filters["brand_variant_attribute"] = (
		frappe.db.get_single_value("SRV Settings", "variant_auto_create_attribute")
		or DEFAULT_BRAND_VARIANT_ATTRIBUTE
	)
	conditions = get_conditions(filters)
	if group_by_item:
		return get_grouped_data(filters, conditions)

	return frappe.db.sql(
		f"""
			SELECT
				soi.item_code,
				soi.item_name,
				soi.item_group,
				{RESOLVED_BRAND_SQL} AS brand,
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
				so.name AS sales_order,
				so.status,
				so.project,
				so.company
			FROM `tabSales Order Item` soi
			INNER JOIN `tabSales Order` so ON so.name = soi.parent
			INNER JOIN `tabItem` item ON item.name = soi.item_code
			LEFT JOIN `tabItem` template ON template.name = item.variant_of
			LEFT JOIN `tabItem Variant Attribute` variant_brand
				ON variant_brand.parent = item.name
				AND variant_brand.attribute = %(brand_variant_attribute)s
			WHERE so.docstatus = 1 {conditions}
			ORDER BY
				({RESOLVED_BRAND_SQL}) IS NULL, {RESOLVED_BRAND_SQL},
				soi.item_name, soi.item_code, so.transaction_date DESC, so.name, soi.idx
		""",
		filters,
		as_dict=True,
	)


def get_grouped_data(filters, conditions):
	return frappe.db.sql(
		f"""
			SELECT
				{RESOLVED_BRAND_SQL} AS brand,
				soi.item_code,
				soi.item_name,
				soi.item_group,
				soi.uom,
				SUM(soi.qty) AS qty,
				soi.stock_uom,
				SUM(soi.stock_qty) AS stock_qty,
				SUM(soi.delivered_qty) AS delivered_qty,
				SUM(GREATEST(soi.stock_qty - soi.delivered_qty, 0)) AS pending_qty,
				COUNT(DISTINCT so.name) AS order_count,
				so.company
			FROM `tabSales Order Item` soi
			INNER JOIN `tabSales Order` so ON so.name = soi.parent
			INNER JOIN `tabItem` item ON item.name = soi.item_code
			LEFT JOIN `tabItem` template ON template.name = item.variant_of
			LEFT JOIN `tabItem Variant Attribute` variant_brand
				ON variant_brand.parent = item.name
				AND variant_brand.attribute = %(brand_variant_attribute)s
			WHERE so.docstatus = 1 {conditions}
			GROUP BY
				{RESOLVED_BRAND_SQL}, soi.item_code, soi.item_name, soi.item_group,
				soi.uom, soi.stock_uom, so.company
			ORDER BY
				({RESOLVED_BRAND_SQL}) IS NULL, {RESOLVED_BRAND_SQL},
				soi.item_name, soi.item_code, soi.uom
		""",
		filters,
		as_dict=True,
	)


def get_conditions(filters):
	conditions = []
	field_map = {
		"company": "so.company",
		"customer": "so.customer",
		"territory": "so.territory",
		"project": "so.project",
		"item_code": "soi.item_code",
	}

	if filters.get("from_date"):
		conditions.append("so.transaction_date >= %(from_date)s")
	if filters.get("to_date"):
		conditions.append("so.transaction_date <= %(to_date)s")
	for fieldname, column in field_map.items():
		if filters.get(fieldname):
			conditions.append(f"{column} = %({fieldname})s")
	if filters.get("customer_group"):
		conditions.append(
			get_descendant_condition("Customer Group", "so.customer_group", "customer_group")
		)
	if filters.get("item_group"):
		conditions.append(get_descendant_condition("Item Group", "soi.item_group", "item_group"))
	if filters.get("brand"):
		conditions.append(f"{RESOLVED_BRAND_SQL} = %(brand)s")
	if filters.get("sales_person"):
		conditions.append(
			"EXISTS (SELECT 1 FROM `tabSales Team` st_filter "
			"WHERE st_filter.parent = so.name AND st_filter.parenttype = 'Sales Order' "
			"AND st_filter.sales_person = %(sales_person)s)"
		)

	return " AND " + " AND ".join(conditions) if conditions else ""
