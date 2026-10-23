from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from srv_erp.selling.order_slip import (
	FINISHED_GOODS_WAREHOUSE,
	ensure_print_permission,
	get_date_heading,
	get_required_stock_html,
	parse_order_names,
)


class TestOrderSlipPermission(FrappeTestCase):
	@patch("srv_erp.selling.order_slip.frappe")
	def test_read_permission_allows_printing(self, frappe):
		frappe.has_permission.side_effect = [False, True]
		order = MagicMock(doctype="Sales Order")

		ensure_print_permission(order)

		self.assertEqual(
			frappe.has_permission.call_args_list,
			[
				call("Sales Order", "read", order),
				call("Sales Order", "print", order),
			],
		)

	@patch("srv_erp.selling.order_slip.frappe")
	def test_missing_read_and_print_permission_is_rejected(self, frappe):
		frappe.has_permission.return_value = False
		order = MagicMock(doctype="Sales Order")

		ensure_print_permission(order)

		order._handle_permission_failure.assert_called_once_with("print")


class TestOrderSlipHelpers(FrappeTestCase):
	@patch("srv_erp.selling.order_slip.frappe.get_all")
	@patch("srv_erp.selling.order_slip.frappe.get_doc")
	def test_required_stock_uses_finished_goods_bin_qty(self, get_doc, get_all):
		item = SimpleNamespace(
			item_code="ITEM-001",
			item_name="Packed Item",
			item_group="Products",
			qty=2,
			delivered_qty=0,
			uom="Packing",
			conversion_factor=12,
			stock_uom="PCs",
		)
		order = SimpleNamespace(
			check_permission=MagicMock(),
			transaction_date="2026-08-01",
			items=[item],
		)
		get_doc.return_value = order
		get_all.return_value = [SimpleNamespace(item_code="ITEM-001", actual_qty=36)]

		with (
			patch("srv_erp.selling.order_slip.frappe.defaults.get_user_default", return_value="Company"),
			patch("srv_erp.selling.order_slip.frappe.render_template", return_value="html") as render,
		):
			result = get_required_stock_html(["SO-0001"])

		self.assertEqual(result, "html")
		get_all.assert_called_once_with(
			"Bin",
			filters={
				"warehouse": FINISHED_GOODS_WAREHOUSE,
				"item_code": ["in", ["ITEM-001"]],
			},
			fields=["item_code", "actual_qty"],
		)
		self.assertEqual(
			render.call_args.args[1]["item_groups"]["Products"][0]["current_stock"],
			3,
		)
		self.assertEqual(
			render.call_args.args[1]["item_groups"]["Products"][0]["uom"],
			"Packing",
		)
		html = frappe.render_template(
			"srv_erp/templates/required_stock.html",
			render.call_args.args[1],
		)
		self.assertIn("Current Stock", html)
		self.assertIn(frappe.format(3, {"fieldtype": "Float"}), html)
		self.assertIn("Packing", html)

	def test_delivery_note_ledger_shows_conversion_factor_and_stock_quantity(self):
		delivery_note = SimpleNamespace(
			name="DN-0001",
			posting_date="2026-08-01",
			currency="INR",
			total=100,
			grand_total=118,
			customer_name="Customer Name",
			items=[
				SimpleNamespace(
					item_code="ITEM-001",
					item_name="Packed Item",
					qty=2,
					uom="Packing",
					conversion_factor=12,
					stock_qty=24,
					stock_uom="PCs",
					rate=50,
				)
			],
		)

		html = frappe.render_template(
			"srv_erp/templates/delivery_note_ledger.html",
			{
				"delivery_notes": [delivery_note],
				"date_heading": "01-08-2026",
				"grand_total": 118,
				"currency": "INR",
			},
		)

		self.assertIn("UOM Conversion Value (Packing)", html)
		self.assertIn("Qty in Stock UOM (PCs)", html)
		self.assertIn("12.00", html)
		self.assertIn("24.00 PCs", html)

	def test_order_slip_template_uses_order_number_and_aligned_item_rows(self):
		order = SimpleNamespace(
			name="SO-0001",
			transaction_date="2026-08-01",
			currency="INR",
			total=300,
			grand_total=354,
			customer="CUST-0001",
			customer_name="Customer Name",
			items=[
				SimpleNamespace(
					item_code="ITEM-001", item_name="First Item", qty=1, uom="Nos", stock_uom="Nos", rate=100
				),
				SimpleNamespace(
					item_code="ITEM-002", item_name="Second Item", qty=2, uom="Nos", stock_uom="Nos", rate=100
				),
			],
		)

		html = frappe.render_template(
			"srv_erp/templates/order_slip_ledger.html",
			{
				"orders": [order],
				"date_heading": "01-08-2026",
				"grand_total": 354,
				"currency": "INR",
			},
		)

		self.assertIn("SO-0001", html)
		self.assertIn("ITEM-001: First Item", html)
		self.assertIn('rowspan="3"', html)
		self.assertEqual(html.count("Customer Name"), 1)
		self.assertNotIn("CUST-0001", html)

	def test_parse_order_names_preserves_selection_order_and_removes_duplicates(self):
		self.assertEqual(
			parse_order_names('["SO-0002", "SO-0001", "SO-0002"]'),
			["SO-0002", "SO-0001"],
		)

	def test_get_date_heading_for_range(self):
		self.assertEqual(
			get_date_heading(["2026-08-01", "2026-08-03"]),
			frappe._("{0} to {1}").format(
				frappe.utils.format_date("2026-08-01"),
				frappe.utils.format_date("2026-08-03"),
			),
		)
