import frappe
from frappe.tests import IntegrationTestCase

from srv_erp.selling.sales_order_discount import (
	apply_sales_order_rate_discount,
	validate_sales_order_discounts,
)


class SalesOrderDiscountRow(frappe._dict):
	def precision(self, fieldname):
		return 2


class TestSalesOrderDiscount(IntegrationTestCase):
	def test_sales_order_discount_percentage_must_be_between_zero_and_hundred(self):
		doc = SalesOrderDiscountDoc(
			{
				"doctype": "Sales Order",
				"items": [
					SalesOrderDiscountRow(
						{
							"idx": 1,
							"srv_discount_percentage": 101,
						}
					)
				],
			}
		)

		with self.assertRaises(frappe.ValidationError):
			validate_sales_order_discounts(doc)

	def test_sales_order_discount_percentage_applies_on_current_rate(self):
		row = SalesOrderDiscountRow(
			{
				"idx": 1,
				"rate": 200,
				"srv_discount_percentage": 10,
			}
		)

		apply_sales_order_rate_discount(row)

		self.assertEqual(row.rate, 180)
		self.assertEqual(row.srv_rate_before_discount, 200)
		self.assertEqual(row.srv_last_discount_percentage, 10)

	def test_sales_order_without_srv_discount_does_not_recalculate_totals(self):
		doc = SalesOrderDiscountDoc(
			{
				"doctype": "Sales Order",
				"items": [
					SalesOrderDiscountRow(
						{
							"idx": 1,
							"rate": 100,
							"discount_percentage": 10,
						}
					)
				],
			}
		)

		validate_sales_order_discounts(doc)

		self.assertFalse(doc.taxes_recalculated)

	def test_sales_order_discount_does_not_compound_on_reapply(self):
		row = SalesOrderDiscountRow(
			{
				"idx": 1,
				"rate": 180,
				"srv_discount_percentage": 10,
				"srv_rate_before_discount": 200,
				"srv_last_discount_percentage": 10,
			}
		)

		apply_sales_order_rate_discount(row)

		self.assertEqual(row.rate, 180)
		self.assertEqual(row.srv_rate_before_discount, 200)

	def test_sales_order_valid_discount_is_allowed(self):
		doc = SalesOrderDiscountDoc(
			{
				"doctype": "Sales Order",
				"items": [
					SalesOrderDiscountRow(
						{
							"idx": 1,
							"rate": 100,
							"srv_discount_percentage": 10,
						}
					)
				],
			}
		)

		validate_sales_order_discounts(doc)


class SalesOrderDiscountDoc(frappe._dict):
	def calculate_taxes_and_totals(self):
		self.taxes_recalculated = True
