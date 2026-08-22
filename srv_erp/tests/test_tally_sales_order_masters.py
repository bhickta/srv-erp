from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from srv_erp.integrations.tally_export import (
	TALLY_RESERVED_GROUPS,
	_ancestor_names,
	_export_accounts,
	_export_cost_centers,
	_export_item_groups,
	_export_items,
	_export_uoms,
	build_sales_order_master_payload,
	get_sales_order_count,
)


class TestSalesOrderMasterExport(TestCase):
	@patch("srv_erp.integrations.tally_export.frappe.db.count", return_value=2)
	@patch("srv_erp.integrations.tally_export._validate_sales_order_filters")
	@patch("srv_erp.integrations.tally_export.frappe.only_for")
	def test_count_accepts_tally_company_form_value(self, only_for, validate_filters, count):
		result = get_sales_order_count(
			"Test Company",
			"2026-08-01",
			"2026-08-31",
			tally_company="Tally Test Company",
		)

		self.assertEqual(result, 2)

	@patch("srv_erp.integrations.tally_export.frappe.get_all")
	def test_reserved_tally_groups_are_referenced_without_self_parenting(self, get_all):
		get_all.return_value = [
			frappe._dict(
				name="Application of Funds (Assets) - TC",
				account_name="Application of Funds (Assets)",
				parent_account=None,
				is_group=1,
				root_type="Asset",
				account_type=None,
				account_currency="INR",
			),
			frappe._dict(
				name="Current Assets - TC",
				account_name="Current Assets",
				parent_account="Application of Funds (Assets) - TC",
				is_group=1,
				root_type="Asset",
				account_type=None,
				account_currency="INR",
			),
			frappe._dict(
				name="Investments - TC",
				account_name="Investments",
				parent_account="Current Assets - TC",
				is_group=1,
				root_type="Asset",
				account_type=None,
				account_currency="INR",
			),
			frappe._dict(
				name="Accounts Receivable - TC",
				account_name="Accounts Receivable",
				parent_account="Current Assets - TC",
				is_group=1,
				root_type="Asset",
				account_type="Receivable",
				account_currency="INR",
			),
		]

		messages = _export_accounts("Test Company", "TC")

		self.assertEqual([message["metadata"]["name"] for message in messages], ["Accounts Receivable"])
		self.assertEqual(messages[0]["name"], "Accounts Receivable")
		self.assertEqual(messages[0]["parent"], "Current Assets")
		self.assertNotEqual(messages[0]["metadata"]["name"], messages[0]["parent"])

	def test_reserved_groups_match_tallyprime_7_1_defaults(self):
		self.assertEqual(
			TALLY_RESERVED_GROUPS,
			{
				"Bank Accounts",
				"Bank OD A/c",
				"Branch / Divisions",
				"Capital Account",
				"Cash-in-Hand",
				"Current Assets",
				"Current Liabilities",
				"Deposits (Asset)",
				"Direct Expenses",
				"Direct Incomes",
				"Duties & Taxes",
				"Fixed Assets",
				"Indirect Expenses",
				"Indirect Incomes",
				"Investments",
				"Loans & Advances (Asset)",
				"Loans (Liability)",
				"Misc. Expenses (ASSET)",
				"Provisions",
				"Purchase Accounts",
				"Reserves & Surplus",
				"Sales Accounts",
				"Secured Loans",
				"Stock-in-Hand",
				"Sundry Creditors",
				"Sundry Debtors",
				"Suspense A/c",
				"Unsecured Loans",
			},
		)

	@patch("srv_erp.integrations.tally_export.frappe.get_all")
	def test_master_names_match_tallyprime_7_native_json(self, get_all):
		get_all.return_value = [
			frappe._dict(
				name="ITEM-1",
				item_name="Item One",
				item_group="Products",
				stock_uom="Nos",
				gst_hsn_code=None,
				description=None,
			)
		]
		item = _export_items({"ITEM-1"})[0]
		self.assertEqual(item["metadata"]["type"], "Stock Item")
		self.assertEqual(item["name"], "ITEM-1")
		self.assertEqual(item["base units"], "Nos")
		self.assertNotIn("baseunits", item)

		get_all.return_value = [
			frappe._dict(name="Products", parent_item_group="All Item Groups", is_group=0)
		]
		group = _export_item_groups({"Products"})[0]
		self.assertEqual(group["metadata"]["type"], "Stock Group")
		self.assertEqual(group["name"], "Products")

		get_all.return_value = [
			frappe._dict(
				name="Main - TC",
				cost_center_name="Main",
				parent_cost_center="Root - TC",
				is_group=0,
			)
		]
		cost_centre = _export_cost_centers("Test Company", "TC")[0]
		self.assertEqual(cost_centre["metadata"]["type"], "Cost Centre")
		self.assertEqual(cost_centre["name"], "Main")

		get_all.return_value = [
			frappe._dict(name="Box", must_be_whole_number=1),
			frappe._dict(name="Nos", must_be_whole_number=1),
		]
		units = _export_uoms({"Box", "Nos"})
		self.assertEqual([unit["originalname"] for unit in units], ["Boxes", "Numbers"])
		self.assertTrue(all(unit["name"] != unit["originalname"] for unit in units))

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
				items=[SimpleNamespace(item_code="MB 499-JASTRA", uom="Nos", warehouse="Stores - TC")],
			)
		]
		get_all.return_value = [frappe._dict(name="MB 499-JASTRA", item_group="Drivers", stock_uom="Nos")]

		payload = build_sales_order_master_payload(
			"Test Company",
			"2026-08-01",
			"2026-08-31",
			tally_company="Tally Test Company",
		)

		export_items.assert_called_once_with({"MB 499-JASTRA"})
		_export_parties.assert_called_once_with("Customer", "Sundry Debtors", "Test Company", {"CUST-1"})
		_export_uoms.assert_called_once_with({"Nos"})
		_export_item_groups.assert_called_once_with({"Drivers"})
		_export_warehouses.assert_called_once_with("Test Company", "TC", {"Stores - TC"})
		self.assertEqual(
			payload["static_variables"],
			[
				{"name": "svMstImportFormat", "value": "jsonex"},
				{"name": "svCurrentCompany", "value": "Tally Test Company"},
			],
		)
