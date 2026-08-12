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
	set_default_warehouse(filters)
	validate_warehouse(filters)
	view = filters.get("view") or ("Item Summary" if cint(filters.get("group_by_item", 1)) else "Detailed")
	columns = get_columns(view)
	data = get_data(filters, view)
	add_selected_uom_columns(columns, data, filters.get("include_uom"))
	return columns, data


def get_columns(view="Detailed"):
	if view == "Item Summary":
		return get_grouped_columns()
	if view == "Sub-total":
		return get_subtotal_columns()

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
		{"label": _("Qty Ordered UOM"), "fieldname": "uom_qty", "fieldtype": "Link", "options": "UOM", "width": 105},
		{"label": _("Stock Available"), "fieldname": "stock_available_qty", "fieldtype": "Float", "width": 115, "convertible": "qty"},
		{"label": _("Stock Available UOM"), "fieldname": "uom_stock_available_qty", "fieldtype": "Link", "options": "UOM", "width": 125},
		{"label": _("Difference (Stock - Ordered)"), "fieldname": "difference_qty", "fieldtype": "Float", "width": 150},
		{"label": _("Difference Stock UOM"), "fieldname": "uom_difference_qty", "fieldtype": "Link", "options": "UOM", "width": 125},
		{"label": _("Stock Qty Delivered"), "fieldname": "stock_delivered_qty", "fieldtype": "Float", "width": 130, "convertible": "qty"},
		{"label": _("Stock Qty Delivered UOM"), "fieldname": "uom_stock_delivered_qty", "fieldtype": "Link", "options": "UOM", "width": 130},
		{"label": _("Stock Qty Pending"), "fieldname": "stock_pending_qty", "fieldtype": "Float", "width": 120, "convertible": "qty"},
		{"label": _("Stock Qty Pending UOM"), "fieldname": "uom_stock_pending_qty", "fieldtype": "Link", "options": "UOM", "width": 125},
		{"label": _("Sales Order"), "fieldname": "sales_order", "fieldtype": "Link", "options": "Sales Order", "width": 130},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
		{"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 120},
		{"label": _("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 120},
	]


def get_subtotal_columns():
	return [
		{"label": _("Sales Order"), "fieldname": "sales_order", "fieldtype": "Link", "options": "Sales Order", "width": 140},
		{"label": _("Item Code"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 130},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 200},
		{"label": _("Brand"), "fieldname": "brand", "fieldtype": "Link", "options": "Brand", "width": 120},
		{"label": _("Qty Ordered"), "fieldname": "qty", "fieldtype": "Float", "width": 115},
		{"label": _("UOM"), "fieldname": "uom_qty", "fieldtype": "Link", "options": "UOM", "width": 90},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 150},
		{"label": _("Order Date"), "fieldname": "transaction_date", "fieldtype": "Date", "width": 105},
		{"label": _("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 120},
	]


def get_grouped_columns():
	return [
		{"label": _("Brand"), "fieldname": "brand", "fieldtype": "Link", "options": "Brand", "width": 120},
		{"label": _("Item Code"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 120},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 180},
		{"label": _("Item Group"), "fieldname": "item_group", "fieldtype": "Link", "options": "Item Group", "width": 120},
		{"label": _("Qty Ordered"), "fieldname": "qty", "fieldtype": "Float", "width": 105},
		{"label": _("Qty Ordered UOM"), "fieldname": "uom_qty", "fieldtype": "Link", "options": "UOM", "width": 105},
		{"label": _("Stock Available"), "fieldname": "stock_available_qty", "fieldtype": "Float", "width": 115, "convertible": "qty"},
		{"label": _("Stock Available UOM"), "fieldname": "uom_stock_available_qty", "fieldtype": "Link", "options": "UOM", "width": 125},
		{"label": _("Difference (Stock - Ordered)"), "fieldname": "difference_qty", "fieldtype": "Float", "width": 150},
		{"label": _("Difference Stock UOM"), "fieldname": "uom_difference_qty", "fieldtype": "Link", "options": "UOM", "width": 125},
		{"label": _("Stock Qty Delivered"), "fieldname": "stock_delivered_qty", "fieldtype": "Float", "width": 130, "convertible": "qty"},
		{"label": _("Stock Qty Delivered UOM"), "fieldname": "uom_stock_delivered_qty", "fieldtype": "Link", "options": "UOM", "width": 130},
		{"label": _("Stock Qty Pending"), "fieldname": "stock_pending_qty", "fieldtype": "Float", "width": 120, "convertible": "qty"},
		{"label": _("Stock Qty Pending UOM"), "fieldname": "uom_stock_pending_qty", "fieldtype": "Link", "options": "UOM", "width": 125},
		{"label": _("Order Count"), "fieldname": "order_count", "fieldtype": "Int", "width": 95},
		{"label": _("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 120},
	]


def get_data(filters, view="Detailed"):
	filters["brand_variant_attribute"] = (
		frappe.db.get_single_value("SRV Settings", "variant_auto_create_attribute")
		or DEFAULT_BRAND_VARIANT_ATTRIBUTE
	)
	conditions = get_conditions(filters)
	if view == "Item Summary":
		return get_grouped_data(filters, conditions)
	if view == "Sub-total":
		return get_subtotal_data(filters, conditions)

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
				soi.uom AS uom_qty,
				soi.qty,
				COALESCE(bin.actual_qty, 0) AS stock_available_qty,
				item.stock_uom AS uom_stock_available_qty,
				COALESCE(bin.actual_qty, 0) - soi.stock_qty AS difference_qty,
				item.stock_uom AS uom_difference_qty,
				soi.delivered_qty AS stock_delivered_qty,
				soi.stock_uom AS uom_stock_delivered_qty,
				GREATEST(soi.stock_qty - soi.delivered_qty, 0) AS stock_pending_qty,
				soi.stock_uom AS uom_stock_pending_qty,
				so.name AS sales_order,
				so.status,
				so.project,
				so.company
			FROM `tabSales Order Item` soi
			INNER JOIN `tabSales Order` so ON so.name = soi.parent
			INNER JOIN `tabItem` item ON item.name = soi.item_code
			LEFT JOIN `tabBin` bin
				ON bin.item_code = soi.item_code AND bin.warehouse = %(warehouse)s
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


def get_subtotal_data(filters, conditions):
	rows = frappe.db.sql(
		f"""
			SELECT
				so.name AS sales_order,
				soi.item_code,
				soi.item_name,
				{RESOLVED_BRAND_SQL} AS brand,
				SUM(soi.qty) AS qty,
				soi.uom AS uom_qty,
				so.customer,
				so.transaction_date,
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
				so.name, soi.item_code, soi.item_name, {RESOLVED_BRAND_SQL},
				soi.uom, so.customer, so.transaction_date, so.company
			ORDER BY so.transaction_date DESC, so.name, MIN(soi.idx)
		""",
		filters,
		as_dict=True,
	)

	return append_sales_order_subtotals(rows)


def append_sales_order_subtotals(rows):
	data = []
	current_order = None
	uom_totals = {}

	for row in rows:
		if current_order and row.sales_order != current_order:
			data.extend(make_subtotal_rows(current_order, uom_totals))
			uom_totals = {}
		current_order = row.sales_order
		uom_totals[row.uom_qty] = uom_totals.get(row.uom_qty, 0) + (row.qty or 0)
		data.append(row)

	if current_order:
		data.extend(make_subtotal_rows(current_order, uom_totals))

	return data


def make_subtotal_rows(sales_order, uom_totals):
	return [
		frappe._dict(
			{
				"sales_order": sales_order,
				"item_name": _("Sub-total"),
				"qty": qty,
				"uom_qty": uom,
				"bold": 1,
			}
		)
		for uom, qty in uom_totals.items()
	]


def get_grouped_data(filters, conditions):
	return frappe.db.sql(
		f"""
			SELECT
				{RESOLVED_BRAND_SQL} AS brand,
				soi.item_code,
				soi.item_name,
				soi.item_group,
				soi.uom AS uom_qty,
				SUM(soi.qty) AS qty,
				MAX(COALESCE(bin.actual_qty, 0)) AS stock_available_qty,
				item.stock_uom AS uom_stock_available_qty,
				MAX(COALESCE(bin.actual_qty, 0)) - SUM(soi.stock_qty) AS difference_qty,
				item.stock_uom AS uom_difference_qty,
				SUM(soi.delivered_qty) AS stock_delivered_qty,
				soi.stock_uom AS uom_stock_delivered_qty,
				SUM(GREATEST(soi.stock_qty - soi.delivered_qty, 0)) AS stock_pending_qty,
				soi.stock_uom AS uom_stock_pending_qty,
				COUNT(DISTINCT so.name) AS order_count,
				so.company
			FROM `tabSales Order Item` soi
			INNER JOIN `tabSales Order` so ON so.name = soi.parent
			INNER JOIN `tabItem` item ON item.name = soi.item_code
			LEFT JOIN `tabBin` bin
				ON bin.item_code = soi.item_code AND bin.warehouse = %(warehouse)s
			LEFT JOIN `tabItem` template ON template.name = item.variant_of
			LEFT JOIN `tabItem Variant Attribute` variant_brand
				ON variant_brand.parent = item.name
				AND variant_brand.attribute = %(brand_variant_attribute)s
			WHERE so.docstatus = 1 {conditions}
			GROUP BY
				{RESOLVED_BRAND_SQL}, soi.item_code, soi.item_name, soi.item_group,
				soi.uom, soi.stock_uom, item.stock_uom, so.company
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
