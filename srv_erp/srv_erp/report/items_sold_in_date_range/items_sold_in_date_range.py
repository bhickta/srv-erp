# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate

from srv_erp.srv_erp.report.hierarchical_filters import get_descendant_condition
from srv_erp.srv_erp.report.uom_utils import add_selected_uom_columns

DEFAULT_BRAND_VARIANT_ATTRIBUTE = "Brand"
BASE_ITEM_VIEW = "Base Item (All Brands)"
RESOLVED_BRAND_SQL = (
	"COALESCE(NULLIF(variant_brand.attribute_value, ''), "
	"NULLIF(item.brand, ''), template.brand)"
)
TEMPLATE_ITEM_SQL = "COALESCE(NULLIF(item.variant_of, ''), dni.item_code)"
NET_SOLD_QTY_SQL = (
	"CASE WHEN COALESCE(dn.is_return, 0) = 1 "
	"THEN -ABS(dni.stock_qty) ELSE ABS(dni.stock_qty) END"
)


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
		{"label": _("Item Code"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 140},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 180},
		{
			"label": _("Item Group"),
			"fieldname": "item_group",
			"fieldtype": "Link",
			"options": "Item Group",
			"width": 130,
		},
		{"label": _("Brand"), "fieldname": "brand", "fieldtype": "Data", "width": 120},
		{
			"label": _("Sold Qty"),
			"fieldname": "stock_qty",
			"fieldtype": "Float",
			"width": 110,
			"convertible": "qty",
		},
		{
			"label": _("Stock UOM"),
			"fieldname": "uom_stock_qty",
			"fieldtype": "Link",
			"options": "UOM",
			"width": 100,
		},
		{
			"label": _("Voucher"),
			"fieldname": "voucher",
			"fieldtype": "Data",
			"width": 240,
		},
		{
			"label": _("Voucher Names"),
			"fieldname": "voucher_names",
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


def get_data(filters):
	filters["brand_variant_attribute"] = (
		frappe.db.get_single_value("SRV Settings", "variant_auto_create_attribute")
		or DEFAULT_BRAND_VARIANT_ATTRIBUTE
	)
	filters["all_brands_label"] = _("All Brands")
	group_by_template = filters.get("show_sales_by") == BASE_ITEM_VIEW
	item_code_sql = TEMPLATE_ITEM_SQL if group_by_template else "dni.item_code"
	item_name_sql = (
		"COALESCE(MAX(template.item_name), MAX(dni.item_name))"
		if group_by_template
		else "MAX(dni.item_name)"
	)
	item_group_sql = (
		"MAX(COALESCE(template.item_group, dni.item_group))"
		if group_by_template
		else "MAX(dni.item_group)"
	)
	if group_by_template:
		brand_sql = (
			"%(brand)s" if filters.get("brand") else "%(all_brands_label)s"
		)
	else:
		brand_sql = f"MAX({RESOLVED_BRAND_SQL})"

	return frappe.db.sql(
		f"""
			SELECT
				{item_code_sql} AS item_code,
				{item_name_sql} AS item_name,
				{item_group_sql} AS item_group,
				{brand_sql} AS brand,
				SUM({NET_SOLD_QTY_SQL}) AS stock_qty,
				MAX(dni.stock_uom) AS uom_stock_qty,
				GROUP_CONCAT(
					DISTINCT dn.name
					ORDER BY dn.name
					SEPARATOR '||'
				) AS voucher_names,
				COUNT(DISTINCT dn.name) AS voucher_count
			FROM `tabDelivery Note Item` dni
			INNER JOIN `tabDelivery Note` dn ON dn.name = dni.parent
			INNER JOIN `tabItem` item ON item.name = dni.item_code
			LEFT JOIN `tabItem` template ON template.name = item.variant_of
			LEFT JOIN `tabItem Variant Attribute` variant_brand
				ON variant_brand.parent = item.name
				AND variant_brand.attribute = %(brand_variant_attribute)s
			WHERE
				dn.docstatus = 1
				{get_conditions(filters)}
			GROUP BY {item_code_sql}
			ORDER BY item_name, item_code
		""",
		filters,
		as_dict=True,
	)


def get_conditions(filters):
	conditions = []
	field_map = {
		"company": "dn.company",
		"territory": "dn.territory",
		"project": "dn.project",
		"item_code": "dni.item_code",
		"sales_order": "dni.against_sales_order",
		"warehouse": "dni.warehouse",
	}

	if filters.get("from_date"):
		conditions.append("dn.posting_date >= %(from_date)s")
	if filters.get("to_date"):
		conditions.append("dn.posting_date <= %(to_date)s")
	for fieldname, column in field_map.items():
		if filters.get(fieldname):
			if (
				fieldname == "item_code"
				and filters.get("show_sales_by") == BASE_ITEM_VIEW
			):
				conditions.append(
					f"{TEMPLATE_ITEM_SQL} = COALESCE(NULLIF(("
					"SELECT selected_item.variant_of "
					"FROM `tabItem` selected_item "
					"WHERE selected_item.name = %(item_code)s"
					"), ''), %(item_code)s)"
				)
			else:
				conditions.append(f"{column} = %({fieldname})s")
	if filters.get("customer_group"):
		conditions.append(
			get_descendant_condition("Customer Group", "dn.customer_group", "customer_group")
		)
	if filters.get("item_group"):
		conditions.append(
			get_descendant_condition("Item Group", "dni.item_group", "item_group")
		)
	if filters.get("brand"):
		conditions.append(f"{RESOLVED_BRAND_SQL} = %(brand)s")
	if filters.get("sales_person"):
		conditions.append(
			"EXISTS ("
			"SELECT 1 FROM `tabSales Team` st_filter "
			"WHERE st_filter.parent = dn.name "
			"AND st_filter.parenttype = 'Delivery Note' "
			"AND st_filter.sales_person = %(sales_person)s)"
		)

	return " AND " + " AND ".join(conditions) if conditions else ""
