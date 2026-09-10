from unittest import TestCase
from unittest.mock import patch

from frappe import _dict

from srv_erp.selling.sales_order_list import (
	LiveCustomerGroupSalesOrderQuery,
	_extract_live_group_bounds,
)


class TestSalesOrderList(TestCase):
	@patch("srv_erp.selling.sales_order_list.frappe")
	def test_extracts_live_group_filter_without_expanding_customers(self, frappe):
		frappe.db.get_value.return_value = (10, 25)
		args = _dict({
			"filters": [
				["Sales Order", "customer_group", "descendants of (inclusive)", "Tour"],
				["Sales Order", "docstatus", "=", 0],
			]
		})

		bounds = _extract_live_group_bounds(args)

		self.assertEqual(bounds, [(10, 25)])
		self.assertEqual(args.filters, [["Sales Order", "docstatus", "=", 0]])
		frappe.db.get_value.assert_called_once_with("Customer Group", "Tour", ["lft", "rgt"])

	@patch("frappe.model.db_query.DatabaseQuery.build_conditions")
	def test_adds_server_side_live_customer_exists_condition(self, build_conditions):
		query = LiveCustomerGroupSalesOrderQuery.__new__(LiveCustomerGroupSalesOrderQuery)
		query.group_bounds = [(10, 25)]
		query.conditions = []

		query.build_conditions()

		build_conditions.assert_called_once()
		condition = query.conditions[0]
		self.assertIn("EXISTS", condition)
		self.assertIn("live_customer_0.name = `tabSales Order`.customer", condition)
		self.assertIn("live_customer_group_0.lft >= 10", condition)
		self.assertIn("live_customer_group_0.rgt <= 25", condition)
		self.assertNotIn(" IN ", condition)

	@patch("frappe.model.db_query.DatabaseQuery.build_conditions")
	def test_unknown_group_matches_nothing(self, build_conditions):
		query = LiveCustomerGroupSalesOrderQuery.__new__(LiveCustomerGroupSalesOrderQuery)
		query.group_bounds = [None]
		query.conditions = []

		query.build_conditions()

		self.assertEqual(query.conditions, ["1 = 0"])
