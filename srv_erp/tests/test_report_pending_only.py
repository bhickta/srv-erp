from unittest import TestCase
from unittest.mock import patch

import frappe

from srv_erp.srv_erp.report.items_delivered_in_date_range.items_delivered_in_date_range import (
	get_conditions as get_delivered_conditions,
)
from srv_erp.srv_erp.report.items_ordered_in_date_range.items_ordered_in_date_range import (
	get_columns as get_ordered_columns,
)
from srv_erp.srv_erp.report.items_ordered_in_date_range.items_ordered_in_date_range import (
	get_conditions as get_ordered_conditions,
)


class TestReportPendingOnly(TestCase):
	def test_pending_filter_can_be_disabled(self):
		self.assertNotIn("stock_qty", get_ordered_conditions(frappe._dict()))
		self.assertNotIn("stock_qty", get_delivered_conditions(frappe._dict()))
		self.assertNotIn("stock_qty", get_ordered_conditions(frappe._dict(pending_only="0")))
		self.assertNotIn("stock_qty", get_delivered_conditions(frappe._dict(pending_only="0")))

	def test_ordered_report_filters_fully_delivered_items(self):
		conditions = get_ordered_conditions(frappe._dict(pending_only=1))

		self.assertIn("soi.qty > COALESCE(soi.delivered_qty, 0)", conditions)

	def test_delivered_report_filters_fully_delivered_items(self):
		conditions = get_delivered_conditions(frappe._dict(pending_only=1))

		self.assertIn(
			"COALESCE(soi.stock_qty, dni.stock_qty)"
			" > COALESCE(soi.delivered_qty, dni.stock_qty)",
			conditions,
		)

	@patch(
		"srv_erp.srv_erp.report.items_ordered_in_date_range.items_ordered_in_date_range._",
		side_effect=lambda value: value,
	)
	def test_ordered_report_labels_manufacturing_quantity_in_all_views(self, _translate):
		for grouped, subtotal in ((False, False), (True, False), (False, True)):
			columns = get_ordered_columns(grouped, subtotal)
			manufacture_column = next(
				column for column in columns if column["fieldname"] == "stock_shortfall_qty"
			)

			self.assertEqual(manufacture_column["label"], "Qty to Manufacture")
			self.assertEqual(
				manufacture_column["description"],
				"Ordered - Delivered - Stock (minimum 0)",
			)
