import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import cint, flt

SHOW_PENDING_QTY_SETTING = "show_pending_qty_in_sales_order"
PENDING_QTY_FIELD = "srv_pending_qty"
SHOW_CURRENT_STOCK_SETTING = "show_current_stock_in_sales_order"
CURRENT_STOCK_FIELD = "srv_current_stock"


def set_sales_order_ui_defaults():
	if frappe.db.get_single_value("SRV Settings", SHOW_PENDING_QTY_SETTING) is None:
		frappe.db.set_single_value("SRV Settings", SHOW_PENDING_QTY_SETTING, 1)
	if frappe.db.get_single_value("SRV Settings", SHOW_CURRENT_STOCK_SETTING) is None:
		frappe.db.set_single_value("SRV Settings", SHOW_CURRENT_STOCK_SETTING, 0)


def configure_sales_order_pending_qty_field(enabled=None):
	if enabled is None:
		enabled = frappe.db.get_single_value("SRV Settings", SHOW_PENDING_QTY_SETTING)
	enabled = cint(enabled)

	create_custom_fields(
		{
			"Sales Order Item": [
				{
					"allow_on_submit": 1,
					"columns": 1,
					"description": "Ordered quantity minus delivered quantity, with a minimum of zero.",
					"fieldname": PENDING_QTY_FIELD,
					"fieldtype": "Float",
					"hidden": 0 if enabled else 1,
					"in_list_view": enabled,
					"insert_after": "qty",
					"label": "Pending Qty",
					"no_copy": 1,
					"non_negative": 1,
					"read_only": 1,
				}
			]
		},
		update=True,
	)

	# Keep the editable grid within Frappe's ten-column width budget when the
	# Pending Qty column is enabled, without dropping any existing SRV columns.
	width = 1 if enabled else 2
	for fieldname in ("delivery_date", "rate"):
		frappe.make_property_setter(
			{
				"doctype": "Sales Order Item",
				"doctype_or_field": "DocField",
				"fieldname": fieldname,
				"property": "columns",
				"value": width,
				"property_type": "Int",
			}
		)

	frappe.clear_cache(doctype="Sales Order Item")


def configure_sales_order_current_stock_field(enabled=None):
	"""Create a virtual grid field, so current stock is never stored on an order item."""
	if enabled is None:
		enabled = frappe.db.get_single_value("SRV Settings", SHOW_CURRENT_STOCK_SETTING)
	enabled = cint(enabled)

	create_custom_fields(
		{
			"Sales Order Item": [
				{
					"allow_on_submit": 1,
					"columns": 1,
					"description": "Live stock in the row warehouse, including child warehouses.",
					"fieldname": CURRENT_STOCK_FIELD,
					"fieldtype": "Float",
					"hidden": 0 if enabled else 1,
					"in_list_view": enabled,
					"insert_after": PENDING_QTY_FIELD,
					"is_virtual": 1,
					"label": "Current Stock",
					"no_copy": 1,
					"read_only": 1,
				}
			]
		},
		update=True,
	)
	frappe.clear_cache(doctype="Sales Order Item")


@frappe.whitelist()
def get_sales_order_item_stock(rows):
	"""Return live stock by client row name without persisting it on Sales Order Item."""
	if frappe.session.user == "Guest" or not frappe.has_permission("Sales Order", ptype="read"):
		frappe.throw("Not permitted", frappe.PermissionError)

	rows = frappe.parse_json(rows)
	if not isinstance(rows, list):
		frappe.throw("Rows must be a list.")
	if len(rows) > 500:
		frappe.throw("Current stock can be loaded for at most 500 rows at a time.")

	valid_rows = [
		row
		for row in rows
		if isinstance(row, dict) and row.get("name") and row.get("item_code") and row.get("warehouse")
	]
	if not valid_rows:
		return {}

	from erpnext.stock.doctype.warehouse.warehouse import get_child_warehouses

	warehouse_members = {
		warehouse: set(get_child_warehouses(warehouse))
		for warehouse in {row["warehouse"] for row in valid_rows}
	}
	item_codes = {row["item_code"] for row in valid_rows}
	all_warehouses = set().union(*warehouse_members.values())
	bins = frappe.get_all(
		"Bin",
		filters={
			"item_code": ["in", list(item_codes)],
			"warehouse": ["in", list(all_warehouses)],
		},
		fields=["item_code", "warehouse", "actual_qty"],
	)

	stock_by_row = {}
	for row in valid_rows:
		warehouses = warehouse_members[row["warehouse"]]
		stock_by_row[row["name"]] = sum(
			flt(bin_row.actual_qty)
			for bin_row in bins
			if bin_row.item_code == row["item_code"] and bin_row.warehouse in warehouses
		)

	return stock_by_row
