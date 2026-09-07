from unittest import TestCase
from unittest.mock import patch

from srv_erp.selling.sales_order_list import _get_customers_in_group


class TestSalesOrderList(TestCase):
	@patch("srv_erp.selling.sales_order_list.get_descendants_of")
	@patch("srv_erp.selling.sales_order_list.frappe")
	def test_resolves_customers_from_current_group_tree(self, frappe, get_descendants):
		frappe.db.exists.return_value = True
		get_descendants.return_value = ["Child A", "Child B"]
		frappe.get_list.return_value = ["CUST-0001", "CUST-0002"]

		customers = _get_customers_in_group("Parent")

		get_descendants.assert_called_once_with("Customer Group", "Parent")
		frappe.get_list.assert_called_once_with(
			"Customer",
			filters={"customer_group": ("in", ["Parent", "Child A", "Child B"])},
			pluck="name",
			limit_page_length=0,
		)
		self.assertEqual(customers, ["CUST-0001", "CUST-0002"])

	@patch("srv_erp.selling.sales_order_list.frappe")
	def test_unknown_group_returns_no_customers(self, frappe):
		frappe.db.exists.return_value = False

		self.assertEqual(_get_customers_in_group("Unknown"), [])
		frappe.get_list.assert_not_called()
