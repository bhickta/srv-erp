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
		self.assertEqual(
			[column["fieldname"] for column in get_columns(subtotal_view=True)],
			["item_code", "brand", "qty", "stock_available_qty", "stock_delivered_qty", "stock_pending_qty"],
		)

	def test_appends_subtotal_after_each_item_code(self):
		rows = [
			frappe._dict(
				item_code="DB 473",
				brand="SRV",
				qty=6,
				stock_available_qty=8,
				stock_delivered_qty=2,
				stock_pending_qty=4,
				stock_uom="Bag",
			),
			frappe._dict(
				item_code="DB 473",
				brand="Amber",
				qty=12,
				stock_available_qty=15,
				stock_delivered_qty=3,
				stock_pending_qty=9,
				stock_uom="Bag",
			),
			frappe._dict(
				item_code="DB 475",
				brand="SRN",
				qty=5,
				stock_available_qty=7,
				stock_delivered_qty=1,
				stock_pending_qty=4,
				stock_uom="Bag",
			),
		]

		result = append_item_code_subtotals(rows)

		self.assertEqual([row.item_code for row in result if row.get("is_group")], ["DB 473", "DB 475"])
		self.assertEqual([row.brand for row in result if row.get("is_total")], ["Total", "Total"])
		self.assertEqual([row.qty for row in result if row.get("is_total")], [18, 5])
		self.assertEqual([row.stock_available_qty for row in result if row.get("is_total")], [23, 7])
		self.assertEqual([row.stock_delivered_qty for row in result if row.get("is_total")], [5, 1])
		self.assertEqual([row.stock_pending_qty for row in result if row.get("is_total")], [13, 4])
		self.assertEqual(sum(not row for row in result), 2)

	def test_keeps_different_uoms_in_separate_subtotals(self):
		rows = [
			frappe._dict(
				item_code="DB 473",
				brand="SRV",
				qty=6,
				stock_available_qty=8,
				stock_delivered_qty=2,
				stock_pending_qty=4,
				stock_uom="Bag",
			),
			frappe._dict(
				item_code="DB 473",
				brand="Loose",
				qty=2,
				stock_available_qty=3,
				stock_delivered_qty=1,
				stock_pending_qty=1,
				stock_uom="Kg",
			),
		]

		subtotals = [row for row in append_item_code_subtotals(rows) if row.get("is_total")]

		self.assertEqual([(row.stock_uom, row.qty) for row in subtotals], [("Bag", 6), ("Kg", 2)])

	def test_accepts_plain_dict_rows_returned_by_database(self):
		rows = [
			{
				"item_code": "DB 473",
				"brand": "SRV",
				"qty": 6,
				"stock_available_qty": 8,
				"stock_delivered_qty": 2,
				"stock_pending_qty": 4,
				"stock_uom": "Bag",
			}
		]

		result = append_item_code_subtotals(rows)

		self.assertEqual(result[0].item_code, "DB 473")
		self.assertEqual(result[1].brand, "SRV")
		self.assertEqual(result[2].qty, 6)
