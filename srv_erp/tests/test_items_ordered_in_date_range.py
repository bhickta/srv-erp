import frappe
from frappe.tests import IntegrationTestCase

from srv_erp.srv_erp.report.items_ordered_in_date_range.items_ordered_in_date_range import (
	append_sales_order_subtotals,
)


class TestItemsOrderedInDateRange(IntegrationTestCase):
	def test_appends_subtotal_after_each_sales_order(self):
		rows = [
			frappe._dict(sales_order="DB 473", item_code="SRV", qty=6, uom_qty="Bag"),
			frappe._dict(sales_order="DB 473", item_code="Amber", qty=12, uom_qty="Bag"),
			frappe._dict(sales_order="DB 475", item_code="SRN", qty=5, uom_qty="Bag"),
		]

		result = append_sales_order_subtotals(rows)

		self.assertEqual([row.item_name for row in result if row.get("bold")], ["Sub-total", "Sub-total"])
		self.assertEqual([row.qty for row in result if row.get("bold")], [18, 5])

	def test_keeps_different_uoms_in_separate_subtotals(self):
		rows = [
			frappe._dict(sales_order="DB 473", item_code="SRV", qty=6, uom_qty="Bag"),
			frappe._dict(sales_order="DB 473", item_code="Loose", qty=2, uom_qty="Kg"),
		]

		subtotals = [row for row in append_sales_order_subtotals(rows) if row.get("bold")]

		self.assertEqual([(row.uom_qty, row.qty) for row in subtotals], [("Bag", 6), ("Kg", 2)])
