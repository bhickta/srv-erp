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
		database = SimpleNamespace(
			sql=Mock(return_value=[]),
			get_single_value=Mock(return_value=None),
		)
		with patch.object(report, "frappe", SimpleNamespace(db=database)):
			get_data(frappe._dict(from_date="2026-10-01", to_date="2026-10-31"))

		query = database.sql.call_args.args[0]
		query_filters = database.sql.call_args.args[1]
		self.assertIn("dn.docstatus = 1", query)
		self.assertIn("COALESCE(dn.is_return, 0) = 0", query)
		self.assertIn("dni.qty > 0", query)
		self.assertIn("dn.posting_date >= %(from_date)s", query)
		self.assertIn("SUM(dni.stock_qty) AS stock_qty", query)
		self.assertIn("MAX(dni.stock_uom) AS uom_stock_qty", query)
		self.assertIn("GROUP_CONCAT(", query)
		self.assertIn("DISTINCT dn.name", query)
		self.assertIn("AS voucher_names", query)
		self.assertIn("COUNT(DISTINCT dn.name) AS voucher_count", query)
		self.assertIn("variant_brand.attribute_value", query)
		self.assertIn("LEFT JOIN `tabItem Variant Attribute` variant_brand", query)
		self.assertEqual(query_filters["brand_variant_attribute"], "Brand")
		self.assertIn("GROUP BY dni.item_code", query)
		self.assertNotIn("dn.name AS delivery_note", query)

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

	def test_brand_filter_applies_without_customer_filter(self):
		conditions = get_conditions(frappe._dict(brand="Acme", customer="Customer-001"))

		self.assertIn("COALESCE(NULLIF(variant_brand.attribute_value, '')", conditions)
		self.assertIn("NULLIF(item.brand, '')", conditions)
		self.assertIn("template.brand) = %(brand)s", conditions)
		self.assertNotIn("dn.customer", conditions)

	def test_quantity_has_uom_conversion_support(self):
		columns = get_columns()
		qty_column = next(column for column in columns if column["fieldname"] == "stock_qty")

		self.assertEqual(qty_column["convertible"], "qty")
		self.assertEqual(
			[column["fieldname"] for column in columns],
			[
				"item_code",
				"item_name",
				"item_group",
				"brand",
				"stock_qty",
				"uom_stock_qty",
				"voucher",
				"voucher_names",
				"voucher_count",
			],
		)
		voucher_column = next(column for column in columns if column["fieldname"] == "voucher")
		self.assertEqual(voucher_column["fieldtype"], "Data")
		voucher_names_column = next(column for column in columns if column["fieldname"] == "voucher_names")
		self.assertEqual(voucher_names_column["hidden"], 1)
		voucher_count_column = next(column for column in columns if column["fieldname"] == "voucher_count")
		self.assertEqual(voucher_count_column["hidden"], 1)

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
