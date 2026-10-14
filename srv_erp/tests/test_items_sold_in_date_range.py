from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from srv_erp.srv_erp.report.items_sold_in_date_range import items_sold_in_date_range as report

get_columns = report.get_columns
get_conditions = report.get_conditions
get_data = report.get_data
validate_filters = report.validate_filters


class TestItemsSoldInDateRange(TestCase):
	def setUp(self):
		translation_patcher = patch(
			"srv_erp.srv_erp.report.items_sold_in_date_range.items_sold_in_date_range._",
			side_effect=lambda value: value,
		)
		translation_patcher.start()
		self.addCleanup(translation_patcher.stop)

	def test_report_uses_submitted_non_return_delivery_notes(self):
		database = SimpleNamespace(sql=Mock(return_value=[]))
		with patch.object(report, "frappe", SimpleNamespace(db=database)):
			get_data(frappe._dict(from_date="2026-10-01", to_date="2026-10-31"))

		query = database.sql.call_args.args[0]
		self.assertIn("dn.docstatus = 1", query)
		self.assertIn("COALESCE(dn.is_return, 0) = 0", query)
		self.assertIn("dni.qty > 0", query)
		self.assertIn("dn.posting_date >= %(from_date)s", query)
		self.assertIn("dni.qty", query)
		self.assertIn("dni.stock_qty", query)

	def test_item_group_and_customer_group_filters_include_descendants(self):
		conditions = get_conditions(
			frappe._dict(item_group="Hardware", customer_group="Retail")
		)

		self.assertIn("SELECT child.name FROM `tabItem Group`", conditions)
		self.assertIn("dni.item_group IN", conditions)
		self.assertIn("SELECT child.name FROM `tabCustomer Group`", conditions)
		self.assertIn("dn.customer_group IN", conditions)

	def test_sales_person_filter_uses_delivery_note_sales_team(self):
		conditions = get_conditions(frappe._dict(sales_person="SP-001"))

		self.assertIn("st_filter.parenttype = 'Delivery Note'", conditions)
		self.assertIn("st_filter.sales_person = %(sales_person)s", conditions)

	def test_quantity_has_uom_conversion_support(self):
		columns = get_columns()
		qty_column = next(column for column in columns if column["fieldname"] == "qty")

		self.assertEqual(qty_column["convertible"], "qty")
		self.assertIn("stock_qty", [column["fieldname"] for column in columns])
		self.assertIn("uom_qty", [column["fieldname"] for column in columns])

	def test_company_and_valid_date_range_are_required(self):
		with patch.object(report.frappe, "throw", side_effect=frappe.ValidationError) as frappe_throw:
			with self.assertRaises(frappe.ValidationError):
				validate_filters(frappe._dict(from_date="2026-10-01", to_date="2026-10-31"))

			with self.assertRaises(frappe.ValidationError):
				validate_filters(
					frappe._dict(
						company="Example Co",
						from_date="2026-10-31",
						to_date="2026-10-01",
					)
				)

		self.assertEqual(frappe_throw.call_count, 2)
