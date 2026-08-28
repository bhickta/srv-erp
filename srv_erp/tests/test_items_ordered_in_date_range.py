from inspect import getsource
from unittest import TestCase
from unittest.mock import patch

import frappe

from srv_erp.srv_erp.report.items_ordered_in_date_range.items_ordered_in_date_range import (
	SO_UOM,
	STOCK_DELIVERED_QTY_SQL,
	STOCK_PENDING_QTY_SQL,
	STOCK_UOM,
	append_item_code_subtotals,
	convert_and_group_subtotal_rows,
	convert_data_to_display_uom,
	get_columns,
	get_grouped_data,
	merge_sales_orders,
)


class TestItemsOrderedInDateRange(TestCase):
	def setUp(self):
		translation_patcher = patch(
			"srv_erp.srv_erp.report.items_ordered_in_date_range.items_ordered_in_date_range._",
			side_effect=lambda value: value,
		)
		translation_patcher.start()
		self.addCleanup(translation_patcher.stop)

	def test_sales_order_delivered_qty_is_converted_to_stock_uom_in_queries(self):
		self.assertIn("soi.delivered_qty", STOCK_DELIVERED_QTY_SQL)
		self.assertIn("soi.conversion_factor", STOCK_DELIVERED_QTY_SQL)
		self.assertIn(STOCK_DELIVERED_QTY_SQL, STOCK_PENDING_QTY_SQL)
		self.assertIn("soi.stock_qty", STOCK_PENDING_QTY_SQL)

	def test_so_uom_is_the_default_for_planning_quantities(self):
		data = [
			frappe._dict(
				item_code="DB 548-KOMAL STAR",
				uom_qty="Box",
				so_conversion_factor=3,
				stock_ordered_qty=51,
				stock_delivered_qty=17,
				stock_available_qty=0,
				stock_pending_qty=34,
				stock_shortfall_qty=34,
				production_uom="Nos",
			)
		]

		convert_data_to_display_uom(data, frappe._dict())

		self.assertEqual(data[0].production_uom, "Box")
		self.assertEqual(data[0].stock_ordered_qty, 17)
		self.assertAlmostEqual(data[0].stock_delivered_qty, 17 / 3)
		self.assertAlmostEqual(data[0].stock_shortfall_qty, 34 / 3)

	def test_stock_uom_can_be_selected(self):
		data = [
			frappe._dict(
				item_code="ITEM-1",
				uom_qty="Box",
				so_conversion_factor=3,
				stock_ordered_qty=51,
				stock_delivered_qty=17,
				production_uom="Nos",
			)
		]

		convert_data_to_display_uom(data, frappe._dict(quantity_uom=STOCK_UOM))

		self.assertEqual(data[0].production_uom, "Nos")
		self.assertEqual(data[0].stock_ordered_qty, 51)
		self.assertEqual(data[0].stock_delivered_qty, 17)

	def test_other_uom_overrides_so_uom_when_conversion_exists(self):
		data = [
			frappe._dict(
				item_code="ITEM-1",
				uom_qty="Box",
				so_conversion_factor=3,
				stock_ordered_qty=100,
				production_uom="Nos",
			)
		]

		convert_data_to_display_uom(
			data,
			frappe._dict(quantity_uom=SO_UOM, include_uom="Carton"),
			conversion_factors={"ITEM-1": 10},
		)

		self.assertEqual(data[0].production_uom, "Carton")
		self.assertEqual(data[0].stock_ordered_qty, 10)

	def test_production_columns_are_prominent_in_all_views(self):
		self.assertEqual(get_columns(False)[0]["fieldname"], "item_code")
		self.assertEqual(get_columns(True)[0]["fieldname"], "brand")
		for grouped in (False, True):
			columns = get_columns(grouped)
			fieldnames = [column["fieldname"] for column in columns]
			self.assertNotIn("qty", fieldnames)
			self.assertNotIn("uom_qty", fieldnames)
			production_fields = [
				"stock_ordered_qty",
				"stock_delivered_qty",
				"stock_available_qty",
				"stock_shortfall_qty",
				"production_uom",
			]
			start = fieldnames.index("stock_ordered_qty")
			self.assertEqual(fieldnames[start : start + 5], production_fields)
			self.assertEqual(
				[columns[start + offset]["label"] for offset in range(4)],
				["Ordered", "Delivered", "Stock", "Qty to Manufacture"],
			)
			self.assertEqual(columns[start + 4]["label"], "UOM")
		self.assertEqual(
			[column["fieldname"] for column in get_columns(subtotal_view=True)],
			[
				"item_code",
				"brand",
				"sales_orders",
				"stock_uom",
				"qty",
				"stock_delivered_qty",
				"stock_available_qty",
				"stock_shortfall_qty",
			],
		)
		self.assertEqual(
			[column["label"] for column in get_columns(subtotal_view=True)[4:]],
			["Ordered", "Delivered", "Stock", "Qty to Manufacture"],
		)
		self.assertIn("sales_orders", [column["fieldname"] for column in get_columns(True)])
		self.assertIn("sales_order", [column["fieldname"] for column in get_columns(False)])
		self.assertNotIn("sales_orders", [column["fieldname"] for column in get_columns(False)])

	def test_grouped_query_collects_sales_orders_without_changing_quantity_grouping(self):
		query = getsource(get_grouped_data)
		self.assertIn(
			"GROUP_CONCAT(DISTINCT so.name ORDER BY so.name SEPARATOR ', ') AS sales_orders",
			query,
		)
		self.assertIn("COUNT(DISTINCT so.name) AS order_count", query)
		self.assertNotIn("so.name, soi.item_code", query.split("GROUP BY", 1)[1])

	def test_sales_order_sources_are_deduplicated_and_sorted(self):
		target = frappe._dict(sales_orders="SAL-ORD-3, SAL-ORD-1")

		merge_sales_orders(target, "SAL-ORD-2, SAL-ORD-1")

		self.assertEqual(target.sales_orders, "SAL-ORD-1, SAL-ORD-2, SAL-ORD-3")

	def test_other_uom_converts_per_item_and_falls_back_safely(self):
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
		self.assertAlmostEqual(amber.stock_shortfall_qty, 0.6)
		self.assertEqual(result[1].stock_shortfall_qty, 0)

	def test_subtotal_view_uses_so_uom_by_default(self):
		rows = [
			{
				"actual_item_code": "DB 548-KOMAL STAR",
				"item_code": "DB 548-KOMAL STAR",
				"brand": "Komal Star",
				"qty": 51,
				"stock_available_qty": 6,
				"stock_delivered_qty": 17,
				"stock_pending_qty": 34,
				"stock_uom": "Nos",
				"so_uom": "Box",
				"so_conversion_factor": 3,
			}
		]

		result = convert_and_group_subtotal_rows(rows, display_mode=SO_UOM)

		self.assertEqual(len(result), 1)
		self.assertEqual(result[0].stock_uom, "Box")
		self.assertEqual(result[0].qty, 17)
		self.assertAlmostEqual(result[0].stock_delivered_qty, 17 / 3)
		self.assertAlmostEqual(result[0].stock_available_qty, 2)
		self.assertAlmostEqual(result[0].stock_shortfall_qty, 28 / 3)

	def test_conversion_occurs_before_brand_aggregation(self):
		rows = [
			{
				"actual_item_code": "ITEM-A",
				"item_code": "DB 473",
				"brand": "Amber",
				"sales_orders": "SAL-ORD-2",
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
				"sales_orders": "SAL-ORD-1, SAL-ORD-2",
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
		self.assertEqual(result[0].stock_shortfall_qty, 4)
		self.assertEqual(result[0].stock_uom, "Box")
		self.assertEqual(result[0].sales_orders, "SAL-ORD-1, SAL-ORD-2")

	def test_appends_subtotal_after_each_item_code(self):
		rows = [
			frappe._dict(
				item_code="DB 473",
				brand="SRV",
				sales_orders="SAL-ORD-2",
				qty=6,
				stock_available_qty=8,
				stock_delivered_qty=2,
				stock_pending_qty=4,
				stock_uom="Bag",
			),
			frappe._dict(
				item_code="DB 473",
				brand="Amber",
				sales_orders="SAL-ORD-1, SAL-ORD-2",
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
		self.assertEqual(
			[row.sales_orders for row in result if row.get("is_total")],
			["SAL-ORD-1, SAL-ORD-2", ""],
		)
		self.assertEqual(sum(not row for row in result), 2)
		self.assertTrue(result[1].is_subtotal_detail)
		self.assertNotIn("indent", result[1])

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
