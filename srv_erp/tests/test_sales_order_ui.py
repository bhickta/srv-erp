from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import call, patch

from srv_erp.selling.sales_order_ui import (
	CURRENT_STOCK_FIELD,
	PENDING_QTY_FIELD,
	SHOW_CURRENT_STOCK_SETTING,
	SHOW_PENDING_QTY_SETTING,
	configure_sales_order_current_stock_field,
	configure_sales_order_pending_qty_field,
	get_sales_order_item_stock,
	set_sales_order_ui_defaults,
)


class TestSalesOrderUI(TestCase):
	@patch("srv_erp.selling.sales_order_ui.frappe")
	def test_pending_qty_column_is_enabled_by_default(self, frappe):
		frappe.db.get_single_value.side_effect = [None, 0]

		set_sales_order_ui_defaults()

		self.assertEqual(
			frappe.db.get_single_value.call_args_list,
			[
				call("SRV Settings", SHOW_PENDING_QTY_SETTING),
				call("SRV Settings", SHOW_CURRENT_STOCK_SETTING),
			],
		)
		frappe.db.set_single_value.assert_called_once_with("SRV Settings", SHOW_PENDING_QTY_SETTING, 1)

	@patch("srv_erp.selling.sales_order_ui.frappe.clear_cache")
	@patch("srv_erp.selling.sales_order_ui.create_custom_fields")
	def test_current_stock_column_is_virtual_and_settings_controlled(self, create_custom_fields, clear_cache):
		configure_sales_order_current_stock_field(1)

		field = create_custom_fields.call_args.args[0]["Sales Order Item"][0]
		self.assertEqual(field["fieldname"], CURRENT_STOCK_FIELD)
		self.assertEqual((field["is_virtual"], field["hidden"], field["in_list_view"]), (1, 0, 1))
		clear_cache.assert_called_once_with(doctype="Sales Order Item")

	@patch(
		"erpnext.stock.doctype.warehouse.warehouse.get_child_warehouses",
		return_value=["Main - S", "Shelf - S"],
	)
	@patch("srv_erp.selling.sales_order_ui.frappe")
	def test_current_stock_is_calculated_live_for_row_warehouse(self, frappe, _get_children):
		frappe.session.user = "stock@example.com"
		frappe.has_permission.return_value = True
		frappe.parse_json.return_value = [{"name": "ROW-1", "item_code": "ITEM-1", "warehouse": "Main - S"}]
		frappe.get_all.return_value = [
			SimpleNamespace(item_code="ITEM-1", warehouse="Main - S", actual_qty=5),
			SimpleNamespace(item_code="ITEM-1", warehouse="Shelf - S", actual_qty=3),
		]

		stock = get_sales_order_item_stock.__wrapped__("[]")

		self.assertEqual(stock, {"ROW-1": 8.0})

	@patch("srv_erp.selling.sales_order_ui.frappe.clear_cache")
	@patch("srv_erp.selling.sales_order_ui.frappe.make_property_setter")
	@patch("srv_erp.selling.sales_order_ui.create_custom_fields")
	def test_enabled_pending_qty_column_fits_existing_grid(
		self, create_custom_fields, make_property_setter, clear_cache
	):
		configure_sales_order_pending_qty_field(1)

		field = create_custom_fields.call_args.args[0]["Sales Order Item"][0]
		self.assertEqual(field["fieldname"], PENDING_QTY_FIELD)
		self.assertEqual((field["hidden"], field["in_list_view"], field["columns"]), (0, 1, 1))
		self.assertEqual(
			make_property_setter.call_args_list,
			[
				call(
					{
						"doctype": "Sales Order Item",
						"doctype_or_field": "DocField",
						"fieldname": fieldname,
						"property": "columns",
						"value": 1,
						"property_type": "Int",
					}
				)
				for fieldname in ("delivery_date", "rate")
			],
		)
		clear_cache.assert_called_once_with(doctype="Sales Order Item")

	@patch("srv_erp.selling.sales_order_ui.frappe.clear_cache")
	@patch("srv_erp.selling.sales_order_ui.frappe.make_property_setter")
	@patch("srv_erp.selling.sales_order_ui.create_custom_fields")
	def test_disabled_pending_qty_column_restores_standard_grid_widths(
		self, create_custom_fields, make_property_setter, clear_cache
	):
		configure_sales_order_pending_qty_field(0)

		field = create_custom_fields.call_args.args[0]["Sales Order Item"][0]
		self.assertEqual((field["hidden"], field["in_list_view"]), (1, 0))
		self.assertEqual(
			[setter.args[0]["value"] for setter in make_property_setter.call_args_list],
			[2, 2],
		)
