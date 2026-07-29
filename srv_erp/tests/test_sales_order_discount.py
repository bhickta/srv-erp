import frappe
from frappe.tests import IntegrationTestCase

from srv_erp.sales_order_discount import validate_sales_order_discounts


class TestSalesOrderDiscount(IntegrationTestCase):
	def test_sales_order_discount_percentage_must_be_between_zero_and_hundred(self):
		doc = frappe._dict(
			{
				"doctype": "Sales Order",
				"items": [
					frappe._dict(
						{
							"idx": 1,
							"discount_percentage": 101,
							"discount_amount": 0,
						}
					)
				],
			}
		)

		with self.assertRaises(frappe.ValidationError):
			validate_sales_order_discounts(doc)

	def test_sales_order_discount_amount_cannot_exceed_item_rate(self):
		doc = frappe._dict(
			{
				"doctype": "Sales Order",
				"items": [
					frappe._dict(
						{
							"idx": 1,
							"discount_percentage": 0,
							"discount_amount": 101,
							"rate_with_margin": 100,
						}
					)
				],
			}
		)

		with self.assertRaises(frappe.ValidationError):
			validate_sales_order_discounts(doc)

	def test_sales_order_valid_discount_is_allowed(self):
		doc = frappe._dict(
			{
				"doctype": "Sales Order",
				"items": [
					frappe._dict(
						{
							"idx": 1,
							"discount_percentage": 10,
							"discount_amount": 10,
							"rate_with_margin": 100,
						}
					)
				],
			}
		)

		validate_sales_order_discounts(doc)
