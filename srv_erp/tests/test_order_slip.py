from types import SimpleNamespace

import frappe
from frappe.tests.utils import FrappeTestCase

from srv_erp.selling.order_slip import get_date_heading, parse_order_names


class TestOrderSlipHelpers(FrappeTestCase):
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
