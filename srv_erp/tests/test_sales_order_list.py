from unittest import TestCase
from unittest.mock import patch

from frappe import _dict
from frappe.model.db_query import validate_generated_query

from srv_erp.selling.sales_order_list import (
	LiveCustomerGroupSalesOrderQuery,
	_extract_live_group_bounds,
	_extract_live_group_names,
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
	def test_adds_live_customer_group_bounds_condition(self, build_conditions):
		query = LiveCustomerGroupSalesOrderQuery.__new__(LiveCustomerGroupSalesOrderQuery)
		query.group_bounds = [(10, 25)]
		query.group_names = []
		query.conditions = []

		query.build_conditions()

		build_conditions.assert_called_once()
		condition = query.conditions[0]
		self.assertIn("live_customer_group.lft >= 10", condition)
		self.assertIn("live_customer_group.rgt <= 25", condition)
		self.assertNotIn(" IN ", condition)

	@patch("frappe.model.db_query.DatabaseQuery.prepare_args")
	def test_joins_live_customer_groups_without_subqueries(self, prepare_args):
		prepare_args.return_value = _dict({"tables": "`tabSales Order`"})
		query = LiveCustomerGroupSalesOrderQuery.__new__(LiveCustomerGroupSalesOrderQuery)
		query.group_bounds = [(10, 25)]
		query.group_names = [["Tour"]]
		query._user_tables = "`tabSales Order`"

		args = query.prepare_args()
		self.assertIn("INNER JOIN `tabCustomer` live_customer", args.tables)
		self.assertIn("INNER JOIN `tabCustomer Group` live_customer_group", args.tables)
		self.assertEqual(query._user_tables, args.tables)

		validate_generated_query(
			"select `tabSales Order`.name "
			f"from {query._user_tables} "
			"where live_customer_group.lft >= 10 "
			"and live_customer_group.rgt <= 25 "
			"and live_customer.customer_group in ('Tour')"
		)

	@patch("frappe.model.db_query.DatabaseQuery.build_conditions")
	def test_unknown_group_matches_nothing(self, build_conditions):
		query = LiveCustomerGroupSalesOrderQuery.__new__(LiveCustomerGroupSalesOrderQuery)
		query.group_bounds = [None]
		query.group_names = []
		query.conditions = []

		query.build_conditions()

		self.assertEqual(query.conditions, ["1 = 0"])

	def test_extracts_multi_select_groups_and_preserves_other_filters(self):
		args = _dict({"filters": [
			["Sales Order", "customer_group", "in", ["Assandh", "Other town"]],
			["Sales Order", "status", "=", "To Deliver and Bill"],
		]})
		self.assertEqual(_extract_live_group_names(args), [["Assandh", "Other town"]])
		self.assertEqual(args.filters, [["Sales Order", "status", "=", "To Deliver and Bill"]])

	def test_accepts_comma_separated_groups(self):
		args = _dict({"filters": [["customer_group", "in", "Assandh,Other town"]]})
		self.assertEqual(_extract_live_group_names(args), [["Assandh", "Other town"]])

	@patch("srv_erp.selling.sales_order_list.frappe")
	@patch("frappe.model.db_query.DatabaseQuery.build_conditions")
	def test_multi_select_queries_current_customer_group(self, build_conditions, frappe):
		frappe.db.escape.side_effect = lambda value: "'" + value.replace("'", "''") + "'"
		query = LiveCustomerGroupSalesOrderQuery.__new__(LiveCustomerGroupSalesOrderQuery)
		query.group_bounds = []
		query.group_names = [["Assandh", "Town's group"]]
		query.conditions = []
		query.build_conditions()
		condition = query.conditions[0]
		self.assertIn("live_customer.customer_group IN ('Assandh', 'Town''s group')", condition)
		self.assertNotIn("`tabSales Order`.customer_group", condition)
		self.assertEqual(frappe.db.escape.call_count, 2)

	@patch("frappe.model.db_query.DatabaseQuery.build_conditions")
	def test_empty_multi_select_matches_nothing(self, build_conditions):
		query = LiveCustomerGroupSalesOrderQuery.__new__(LiveCustomerGroupSalesOrderQuery)
		query.group_bounds = []
		query.group_names = [[]]
		query.conditions = []
		query.build_conditions()
		self.assertEqual(query.conditions, ["1 = 0"])
