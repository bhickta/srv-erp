from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from srv_erp.integrations.tally_export import (
	_ancestor_names,
	_master_payload,
	build_sales_order_master_payload,
)


class TestSalesOrderMasterExport(TestCase):
	def test_master_payload_includes_object_level_name_for_tally_import(self):
		payload = _master_payload(
			[
				{
					"metadata": {
						"type": "Group",
						"name": "Current Assets",
						"reservedname": "",
					},
					"parent": "Primary",
				}
			]
		)

		master = payload["tallymessage"][0]
		self.assertEqual(master["name"], "Current Assets")
		self.assertEqual(master["metadata"]["name"], master["name"])

	def test_master_dependencies_include_item_group_ancestors(self):
		rows = [
			frappe._dict(name="Electrical", parent_item_group="All Item Groups"),
			frappe._dict(name="Drivers", parent_item_group="Electrical"),
			frappe._dict(name="LED Drivers", parent_item_group="Drivers"),
		]

		self.assertEqual(
			_ancestor_names(rows, {"LED Drivers"}, "parent_item_group", "All Item Groups"),
			{"Electrical", "Drivers", "LED Drivers"},
		)

	@patch("srv_erp.integrations.tally_export._company_abbr", return_value="TC")
	@patch("srv_erp.integrations.tally_export._export_items", return_value=[])
	@patch("srv_erp.integrations.tally_export._export_warehouses", return_value=[])
	@patch("srv_erp.integrations.tally_export._export_item_groups", return_value=[])
	@patch("srv_erp.integrations.tally_export._export_uoms", return_value=[])
	@patch("srv_erp.integrations.tally_export._export_parties", return_value=[])
	@patch("srv_erp.integrations.tally_export._export_accounts", return_value=[])
	@patch("srv_erp.integrations.tally_export.frappe.get_all")
	@patch("srv_erp.integrations.tally_export._get_sales_orders")
	def test_required_masters_use_exact_sales_order_items(
		self,
		get_orders,
		get_all,
		_export_accounts,
		_export_parties,
		_export_uoms,
		_export_item_groups,
		_export_warehouses,
		export_items,
		_company_abbr,
	):
		get_orders.return_value = [
			SimpleNamespace(
				customer="CUST-1",
				items=[
					SimpleNamespace(item_code="MB 499-JASTRA", uom="Nos", warehouse="Stores - TC")
				],
			)
		]
		get_all.return_value = [
			frappe._dict(name="MB 499-JASTRA", item_group="Drivers", stock_uom="Nos")
		]

		build_sales_order_master_payload("Test Company", "2026-08-01", "2026-08-31")

		export_items.assert_called_once_with({"MB 499-JASTRA"})
		_export_parties.assert_called_once_with("Customer", "Sundry Debtors", "Test Company", {"CUST-1"})
		_export_uoms.assert_called_once_with({"Nos"})
		_export_item_groups.assert_called_once_with({"Drivers"})
		_export_warehouses.assert_called_once_with("Test Company", "TC", {"Stores - TC"})
