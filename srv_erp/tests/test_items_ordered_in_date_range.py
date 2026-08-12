import frappe
from frappe.tests import IntegrationTestCase

from srv_erp.srv_erp.report.items_ordered_in_date_range.items_ordered_in_date_range import (
	append_sales_order_subtotals,
	get_columns,
)


class TestItemsOrderedInDateRange(IntegrationTestCase):
	def test_existing_detailed_and_item_summary_columns_remain_available(self):
		self.assertEqual(get_columns(False)[0]["fieldname"], "item_code")
		self.assertEqual(get_columns(True)[0]["fieldname"], "brand")

	def test_appends_subtotal_after_each_sales_order(self):
		rows = [
			frappe._dict(sales_order="DB 473", item_code="SRV", qty=6, uom_qty="Bag"),
			frappe._dict(sales_order="DB 473", item_code="Amber", qty=12, uom_qty="Bag"),
			frappe._dict(sales_order="DB 475", item_code="SRN", qty=5, uom_qty="Bag"),
		]

		result = append_sales_order_subtotals(rows)

		self.assertEqual([row.sales_order for row in result if row.get("is_group")], ["DB 473", "DB 475"])
		self.assertEqual([row.item_name for row in result if row.get("is_total")], ["Total DB 473", "Total DB 475"])
		self.assertEqual([row.qty for row in result if row.get("is_total")], [18, 5])
		self.assertEqual(sum(not row for row in result), 2)

	def test_keeps_different_uoms_in_separate_subtotals(self):
		rows = [
			frappe._dict(sales_order="DB 473", item_code="SRV", qty=6, uom_qty="Bag"),
			frappe._dict(sales_order="DB 473", item_code="Loose", qty=2, uom_qty="Kg"),
		]

		subtotals = [row for row in append_sales_order_subtotals(rows) if row.get("is_total")]

		self.assertEqual([(row.uom_qty, row.qty) for row in subtotals], [("Bag", 6), ("Kg", 2)])
