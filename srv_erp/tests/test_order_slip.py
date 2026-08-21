import frappe
from frappe.tests.utils import FrappeTestCase

from srv_erp.selling.order_slip import get_date_heading, parse_order_names


class TestOrderSlipHelpers(FrappeTestCase):
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
