from unittest import TestCase
from unittest.mock import patch

from srv_erp.srv_erp.report.items_delivered_in_date_range.items_delivered_in_date_range import (
	STOCK_DELIVERED_QTY_SQL,
	STOCK_ORDERED_QTY_SQL,
	get_columns,
)


class TestItemsDeliveredInDateRange(TestCase):
	def setUp(self):
		translation_patcher = patch(
			"srv_erp.srv_erp.report.items_delivered_in_date_range.items_delivered_in_date_range._",
			side_effect=lambda value: value,
		)
		translation_patcher.start()
		self.addCleanup(translation_patcher.stop)

	def test_sales_order_delivered_qty_is_converted_to_stock_uom(self):
		self.assertIn("soi.delivered_qty", STOCK_DELIVERED_QTY_SQL)
		self.assertIn("soi.conversion_factor", STOCK_DELIVERED_QTY_SQL)
		self.assertIn("dni.stock_qty", STOCK_DELIVERED_QTY_SQL)
		self.assertIn("soi.stock_qty", STOCK_ORDERED_QTY_SQL)

	def test_production_columns_are_prominent(self):
		columns = get_columns()
		fieldnames = [column["fieldname"] for column in columns]
		start = fieldnames.index("stock_ordered_qty")
		self.assertEqual(
			fieldnames[start : start + 5],
			[
				"stock_ordered_qty",
				"stock_delivered_qty",
				"stock_available_qty",
				"stock_shortfall_qty",
				"production_uom",
			],
		)
		self.assertEqual(
			[columns[start + offset]["label"] for offset in range(4)],
			["Ordered", "Delivered", "Stock", "To Produce"],
		)
		self.assertEqual(
			columns[start + 3]["description"],
			"Ordered - Delivered - Stock (minimum 0)",
		)
