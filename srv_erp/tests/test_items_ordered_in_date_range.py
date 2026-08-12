from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from srv_erp.srv_erp.report.items_ordered_in_date_range.items_ordered_in_date_range import (
	add_report_uom_columns,
	append_item_code_subtotals,
	convert_and_group_subtotal_rows,
	get_columns,
)


class TestItemsOrderedInDateRange(IntegrationTestCase):
	@patch(
		"srv_erp.srv_erp.report.items_ordered_in_date_range.items_ordered_in_date_range.add_selected_uom_columns"
	)
	def test_subtotal_view_skips_additional_uom_columns(self, add_selected_uom_columns):
		add_report_uom_columns([], [{}], frappe._dict(subtotal_view=1, include_uom="Box"))

		add_selected_uom_columns.assert_not_called()

	@patch(
		"srv_erp.srv_erp.report.items_ordered_in_date_range.items_ordered_in_date_range.add_selected_uom_columns"
	)
	def test_existing_views_keep_additional_uom_columns(self, add_selected_uom_columns):
		columns = []
		data = []
		add_report_uom_columns(columns, data, frappe._dict(subtotal_view=0, include_uom="Box"))

		add_selected_uom_columns.assert_called_once_with(columns, data, "Box")

	def test_existing_detailed_and_item_summary_columns_remain_available(self):
		self.assertEqual(get_columns(False)[0]["fieldname"], "item_code")
		self.assertEqual(get_columns(True)[0]["fieldname"], "brand")
		self.assertEqual(
			[column["fieldname"] for column in get_columns(subtotal_view=True)],
			["item_code", "brand", "qty", "stock_available_qty", "stock_delivered_qty", "stock_pending_qty"],
		)
		self.assertEqual(
			[column["label"] for column in get_columns(subtotal_view=True)[2:]],
			[
				"Ordered (Qty + UOM)",
				"Stock (Qty + UOM)",
				"Delivered (Qty + UOM)",
				"Remaining (Qty + UOM)",
			],
		)

	def test_preferred_uom_converts_per_item_and_falls_back_safely(self):
		rows = [
			{
				"actual_item_code": "DB-473-AMBER",
				"item_code": "DB 473",
				"brand": "Amber",
				"qty": 20,
				"stock_available_qty": 10,
				"stock_delivered_qty": 4,
				"stock_pending_qty": 16,
				"stock_uom": "Nos",
			},
			{
				"actual_item_code": "DB-473-SRV",
				"item_code": "DB 473",
				"brand": "SRV",
				"qty": 6,
				"stock_available_qty": 8,
				"stock_delivered_qty": 2,
				"stock_pending_qty": 4,
				"stock_uom": "Bag",
			},
		]

		result = convert_and_group_subtotal_rows(
			rows, selected_uom="Box", conversion_factors={"DB-473-AMBER": 10}
		)

		self.assertEqual(
			[(row.brand, row.stock_uom, row.qty) for row in result],
			[("Amber", "Box", 2), ("SRV", "Bag", 6)],
		)
		amber = result[0]
		self.assertEqual(
			(amber.stock_available_qty, amber.stock_delivered_qty, amber.stock_pending_qty),
			(1, 0.4, 1.6),
		)

	def test_conversion_occurs_before_brand_aggregation(self):
		rows = [
			{
				"actual_item_code": "ITEM-A",
				"item_code": "DB 473",
				"brand": "Amber",
				"qty": 10,
				"stock_available_qty": 0,
				"stock_delivered_qty": 0,
				"stock_pending_qty": 10,
				"stock_uom": "Nos",
			},
			{
				"actual_item_code": "ITEM-B",
				"item_code": "DB 473",
				"brand": "Amber",
				"qty": 20,
				"stock_available_qty": 0,
				"stock_delivered_qty": 0,
				"stock_pending_qty": 20,
				"stock_uom": "Nos",
			},
		]

		result = convert_and_group_subtotal_rows(
			rows, selected_uom="Box", conversion_factors={"ITEM-A": 5, "ITEM-B": 10}
		)

		self.assertEqual(len(result), 1)
		self.assertEqual(result[0].qty, 4)
		self.assertEqual(result[0].stock_uom, "Box")

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
