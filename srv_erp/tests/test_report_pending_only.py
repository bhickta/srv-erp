from unittest import TestCase

import frappe

from srv_erp.srv_erp.report.items_delivered_in_date_range.items_delivered_in_date_range import (
	get_conditions as get_delivered_conditions,
)
from srv_erp.srv_erp.report.items_ordered_in_date_range.items_ordered_in_date_range import (
	get_conditions as get_ordered_conditions,
)


class TestReportPendingOnly(TestCase):
	def test_pending_filter_is_off_by_default(self):
		self.assertNotIn("stock_qty", get_ordered_conditions(frappe._dict()))
		self.assertNotIn("stock_qty", get_delivered_conditions(frappe._dict()))
		self.assertNotIn("stock_qty", get_ordered_conditions(frappe._dict(pending_only="0")))
		self.assertNotIn("stock_qty", get_delivered_conditions(frappe._dict(pending_only="0")))

	def test_ordered_report_filters_fully_delivered_items(self):
		conditions = get_ordered_conditions(frappe._dict(pending_only=1))

		self.assertIn("soi.stock_qty > soi.delivered_qty", conditions)

	def test_delivered_report_filters_fully_delivered_items(self):
		conditions = get_delivered_conditions(frappe._dict(pending_only=1))

		self.assertIn(
			"COALESCE(soi.stock_qty, dni.stock_qty)"
			" > COALESCE(soi.delivered_qty, dni.stock_qty)",
			conditions,
		)
