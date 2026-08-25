from unittest import TestCase
from unittest.mock import call, patch

from srv_erp.selling.sales_order_ui import (
	PENDING_QTY_FIELD,
	SHOW_PENDING_QTY_SETTING,
	configure_sales_order_pending_qty_field,
	set_sales_order_ui_defaults,
)


class TestSalesOrderUI(TestCase):
	@patch("srv_erp.selling.sales_order_ui.frappe")
	def test_pending_qty_column_is_enabled_by_default(self, frappe):
		frappe.db.get_single_value.return_value = None

		set_sales_order_ui_defaults()

		frappe.db.get_single_value.assert_called_once_with("SRV Settings", SHOW_PENDING_QTY_SETTING)
		frappe.db.set_single_value.assert_called_once_with("SRV Settings", SHOW_PENDING_QTY_SETTING, 1)

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
