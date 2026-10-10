import frappe
from frappe import _
from frappe.query_builder.functions import Sum
from frappe.utils import cint, flt
from frappe.utils.nestedset import get_descendants_of


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{
			"label": _("Item"),
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "Item",
			"width": 150,
		},
		{
			"label": _("Item Name"),
			"fieldname": "item_name",
			"fieldtype": "Data",
			"width": 200,
		},
		{
			"label": _("Item Group"),
			"fieldname": "item_group",
			"fieldtype": "Link",
			"options": "Item Group",
			"width": 140,
		},
		{
			"label": _("Stock UOM"),
			"fieldname": "stock_uom",
			"fieldtype": "Link",
			"options": "UOM",
			"width": 90,
		},
		{
			"label": _("Current Stock"),
			"fieldname": "current_stock",
			"fieldtype": "Float",
			"width": 120,
		},
		{
			"label": _("Maximum Stock"),
			"fieldname": "maximum_stock",
			"fieldtype": "Float",
			"width": 120,
		},
		{
			"label": _("Excess Qty"),
			"fieldname": "excess_qty",
			"fieldtype": "Float",
			"width": 110,
		},
	]


def get_data(filters):
	items = get_items_with_maximum_stock(filters)
	if not items:
		return []

	stock_by_item = get_current_stock(filters, [item.item_code for item in items])
	only_exceeded = cint(filters.get("only_exceeded", 1))

	data = []
	for item in items:
		current_stock = flt(stock_by_item.get(item.item_code))
		maximum_stock = flt(item.maximum_stock)
		excess_qty = current_stock - maximum_stock

		if only_exceeded and excess_qty <= 0:
			continue

		data.append(
			{
				"item_code": item.item_code,
				"item_name": item.item_name,
				"item_group": item.item_group,
				"stock_uom": item.stock_uom,
				"current_stock": current_stock,
				"maximum_stock": maximum_stock,
				"excess_qty": excess_qty,
			}
		)

	data.sort(key=lambda row: row["excess_qty"], reverse=True)
	return data


def get_items_with_maximum_stock(filters):
	item_filters = {"maximum_stock": (">", 0)}

	if not cint(filters.get("include_disabled_items")):
		item_filters["disabled"] = 0

	if filters.get("item_group"):
		item_filters["item_group"] = ("in", get_item_group_scope(filters.item_group))

	if filters.get("item_code"):
		item_filters["name"] = ("in", as_list(filters.item_code))

	return frappe.get_all(
		"Item",
		filters=item_filters,
		fields=["name as item_code", "item_name", "item_group", "stock_uom", "maximum_stock"],
		order_by="name",
	)


def get_current_stock(filters, item_codes):
	bin_details = frappe.qb.DocType("Bin")
	total_qty = Sum(bin_details.actual_qty)

	query = frappe.qb.from_(bin_details).select(
		bin_details.item_code,
		total_qty.as_("current_stock"),
	)

	if filters.get("company"):
		warehouse = frappe.qb.DocType("Warehouse")
		query = (
			query.join(warehouse)
			.on(warehouse.name == bin_details.warehouse)
			.where(warehouse.company == filters.company)
		)

	query = query.where(bin_details.item_code.isin(item_codes))

	if filters.get("warehouse"):
		query = query.where(bin_details.warehouse.isin(get_warehouse_scope(filters.warehouse)))

	query = query.groupby(bin_details.item_code)

	return {row.item_code: flt(row.current_stock) for row in query.run(as_dict=True)}


def get_item_group_scope(item_group):
	scope = [item_group]
	scope.extend(get_descendants_of("Item Group", item_group, ignore_permissions=True) or [])
	return list(dict.fromkeys(scope))


def get_warehouse_scope(warehouse):
	warehouses = as_list(warehouse)
	scope = list(warehouses)
	for name in warehouses:
		scope.extend(get_descendants_of("Warehouse", name, ignore_permissions=True) or [])
	return list(dict.fromkeys(scope))


def as_list(value):
	if not value:
		return []

	if isinstance(value, str):
		parsed = frappe.parse_json(value)
		if isinstance(parsed, str):
			return [parsed]
		return list(parsed)

	return list(value)
