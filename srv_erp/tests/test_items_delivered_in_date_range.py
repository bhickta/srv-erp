from frappe.tests import IntegrationTestCase

from srv_erp.srv_erp.report.items_delivered_in_date_range.items_delivered_in_date_range import (
	get_columns,
)


class TestItemsDeliveredInDateRange(IntegrationTestCase):
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
