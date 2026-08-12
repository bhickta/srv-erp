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
	group_by_item = cint(filters.get("group_by_item", 1))
	subtotal_view = cint(filters.get("subtotal_view"))
	columns = get_columns(group_by_item, subtotal_view)
	data = get_data(filters, group_by_item, subtotal_view)
	add_report_uom_columns(columns, data, filters)
	return columns, data


def add_report_uom_columns(columns, data, filters):
	if cint(filters.get("subtotal_view")):
		return

	add_selected_uom_columns(columns, data, filters.get("include_uom"))


def get_columns(group_by_item=False, subtotal_view=False):
	if subtotal_view:
		return get_subtotal_columns()
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
		{"label": _("Item Code"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 180},
		{"label": _("Brand"), "fieldname": "brand", "fieldtype": "Link", "options": "Brand", "width": 180},
		{"label": _("Ordered"), "fieldname": "qty", "fieldtype": "Float", "width": 120},
		{"label": _("Stock"), "fieldname": "stock_available_qty", "fieldtype": "Float", "width": 120},
		{"label": _("Delivered"), "fieldname": "stock_delivered_qty", "fieldtype": "Float", "width": 120},
		{"label": _("Remaining"), "fieldname": "stock_pending_qty", "fieldtype": "Float", "width": 120},
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


def get_data(filters, group_by_item=False, subtotal_view=False):
	filters["brand_variant_attribute"] = (
		frappe.db.get_single_value("SRV Settings", "variant_auto_create_attribute")
		or DEFAULT_BRAND_VARIANT_ATTRIBUTE
	)
	conditions = get_conditions(filters)
	if subtotal_view:
		return get_subtotal_data(filters, conditions)
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
				ordered.item_code,
				ordered.brand,
				ordered.qty,
				COALESCE(stock.stock_available_qty, 0) AS stock_available_qty,
				ordered.stock_delivered_qty,
				ordered.stock_pending_qty,
				ordered.stock_uom
			FROM (
				SELECT
					COALESCE(NULLIF(item.variant_of, ''), soi.item_code) AS item_code,
					{RESOLVED_BRAND_SQL} AS brand,
					SUM(soi.stock_qty) AS qty,
					SUM(soi.delivered_qty) AS stock_delivered_qty,
					SUM(GREATEST(soi.stock_qty - soi.delivered_qty, 0)) AS stock_pending_qty,
					soi.stock_uom
				FROM `tabSales Order Item` soi
				INNER JOIN `tabSales Order` so ON so.name = soi.parent
				INNER JOIN `tabItem` item ON item.name = soi.item_code
				LEFT JOIN `tabItem` template ON template.name = item.variant_of
				LEFT JOIN `tabItem Variant Attribute` variant_brand
					ON variant_brand.parent = item.name
					AND variant_brand.attribute = %(brand_variant_attribute)s
				WHERE so.docstatus = 1 {conditions}
				GROUP BY
					COALESCE(NULLIF(item.variant_of, ''), soi.item_code),
					{RESOLVED_BRAND_SQL}, soi.stock_uom
			) ordered
			LEFT JOIN (
				SELECT
					COALESCE(NULLIF(stock_item.variant_of, ''), stock_item.name) AS item_code,
					COALESCE(
						NULLIF(stock_variant_brand.attribute_value, ''),
						NULLIF(stock_item.brand, ''),
						stock_template.brand
					) AS brand,
					stock_item.stock_uom,
					SUM(COALESCE(stock_bin.actual_qty, 0)) AS stock_available_qty
				FROM `tabItem` stock_item
				LEFT JOIN `tabItem` stock_template ON stock_template.name = stock_item.variant_of
				LEFT JOIN `tabItem Variant Attribute` stock_variant_brand
					ON stock_variant_brand.parent = stock_item.name
					AND stock_variant_brand.attribute = %(brand_variant_attribute)s
				LEFT JOIN `tabBin` stock_bin
					ON stock_bin.item_code = stock_item.name
					AND stock_bin.warehouse = %(warehouse)s
				GROUP BY
					COALESCE(NULLIF(stock_item.variant_of, ''), stock_item.name),
					COALESCE(
						NULLIF(stock_variant_brand.attribute_value, ''),
						NULLIF(stock_item.brand, ''),
						stock_template.brand
					),
					stock_item.stock_uom
			) stock
				ON stock.item_code = ordered.item_code
				AND stock.brand <=> ordered.brand
				AND stock.stock_uom = ordered.stock_uom
			ORDER BY ordered.item_code, ordered.brand
		""",
		filters,
		as_dict=True,
	)

	return append_item_code_subtotals(rows)


def append_item_code_subtotals(rows):
	data = []
	current_item_code = None
	uom_totals = {}
	quantity_fields = ("qty", "stock_available_qty", "stock_delivered_qty", "stock_pending_qty")

	for row in rows:
		row = frappe._dict(row)
		item_code = row.get("item_code")
		stock_uom = row.get("stock_uom")

		if current_item_code and item_code != current_item_code:
			data.extend(make_subtotal_rows(uom_totals))
			data.append({})
			uom_totals = {}
		if item_code != current_item_code:
			data.append(make_group_row(row))
		current_item_code = item_code
		uom_total = uom_totals.setdefault(stock_uom, {fieldname: 0 for fieldname in quantity_fields})
		for fieldname in quantity_fields:
			uom_total[fieldname] += row.get(fieldname) or 0
		row["item_code"] = None
		row["indent"] = 1
		data.append(row)

	if current_item_code:
		data.extend(make_subtotal_rows(uom_totals))
		data.append({})

	return data


def make_group_row(row):
	return frappe._dict(
		{
			"item_code": row.item_code,
			"is_group": 1,
		}
	)


def make_subtotal_rows(uom_totals):
	return [
		frappe._dict(
			{
				"brand": _("Total"),
				**totals,
				"stock_uom": uom,
				"is_total": 1,
			}
		)
		for uom, totals in uom_totals.items()
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
