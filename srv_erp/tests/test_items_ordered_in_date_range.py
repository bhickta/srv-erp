import frappe
from frappe.tests import IntegrationTestCase

from srv_erp.srv_erp.report.items_ordered_in_date_range.items_ordered_in_date_range import (
	append_item_code_subtotals,
	get_columns,
)


class TestItemsOrderedInDateRange(IntegrationTestCase):
	def test_existing_detailed_and_item_summary_columns_remain_available(self):
		self.assertEqual(get_columns(False)[0]["fieldname"], "item_code")
		self.assertEqual(get_columns(True)[0]["fieldname"], "brand")

	def test_appends_subtotal_after_each_item_code(self):
		rows = [
			frappe._dict(item_code="DB 473", item_name="DB 473", brand="SRV", qty=6, uom_qty="Bag"),
			frappe._dict(item_code="DB 473", item_name="DB 473", brand="Amber", qty=12, uom_qty="Bag"),
			frappe._dict(item_code="DB 475", item_name="DB 475", brand="SRN", qty=5, uom_qty="Bag"),
		]

		result = append_item_code_subtotals(rows)

		self.assertEqual([row.item_code for row in result if row.get("is_group")], ["DB 473", "DB 475"])
		self.assertEqual([row.brand for row in result if row.get("is_total")], ["Total", "Total"])
		self.assertEqual([row.qty for row in result if row.get("is_total")], [18, 5])
		self.assertEqual(sum(not row for row in result), 2)

	def test_keeps_different_uoms_in_separate_subtotals(self):
		rows = [
			frappe._dict(item_code="DB 473", item_name="DB 473", brand="SRV", qty=6, uom_qty="Bag"),
			frappe._dict(item_code="DB 473", item_name="DB 473", brand="Loose", qty=2, uom_qty="Kg"),
		]

		subtotals = [row for row in append_item_code_subtotals(rows) if row.get("is_total")]

		self.assertEqual([(row.uom_qty, row.qty) for row in subtotals], [("Bag", 6), ("Kg", 2)])
