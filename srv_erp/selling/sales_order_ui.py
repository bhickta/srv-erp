import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import cint


SHOW_PENDING_QTY_SETTING = "show_pending_qty_in_sales_order"
PENDING_QTY_FIELD = "srv_pending_qty"


def set_sales_order_ui_defaults():
	if frappe.db.get_single_value("SRV Settings", SHOW_PENDING_QTY_SETTING) is None:
		frappe.db.set_single_value("SRV Settings", SHOW_PENDING_QTY_SETTING, 1)


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
