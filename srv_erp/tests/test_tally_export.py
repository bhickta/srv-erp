import json

import frappe
from erpnext.tests.utils import ERPNextTestSuite

from srv_erp.integrations.tally_export import (
	SUPPORTED_MASTER_DOCTYPES,
	_clean_name,
	_ledger,
	_parse_doctypes,
	_sales_order_voucher,
	_tally_date,
	_quantity,
)


class TestTallyExport(ERPNextTestSuite):
	def test_clean_name_removes_only_company_suffix(self):
		self.assertEqual(_clean_name("Cash - SRV", "SRV"), "Cash")
		self.assertEqual(_clean_name("Cash SRV", "SRV"), "Cash SRV")

	def test_party_ledger_contains_tally_metadata_and_gstin(self):
		row = _ledger(
			"_Test Customer",
			"Sundry Debtors",
			billwise=True,
			tax_id="07ABCDE1234F1Z5",
			country="India",
		)

		self.assertEqual(row["metadata"]["type"], "Ledger")
		self.assertEqual(row["parent"], "Sundry Debtors")
		self.assertTrue(row["isbillwiseon"])
		self.assertEqual(row["partygstin"], "07ABCDE1234F1Z5")

	def test_doctype_parameter_is_parsed_and_validated(self):
		selected = ["Account", "Customer"]
		self.assertEqual(_parse_doctypes(json.dumps(selected)), selected)
		self.assertEqual(set(SUPPORTED_MASTER_DOCTYPES), {
			"Account", "Customer", "Supplier", "Cost Center",
			"UOM", "Item Group", "Warehouse", "Item",
		})

		with self.assertRaises(frappe.ValidationError):
			_parse_doctypes(json.dumps({"Account": True}))

	def test_sales_order_voucher_uses_tally_order_structure(self):
		order = frappe._dict(
			name="SAL-ORD-TEST-1",
			customer="_Test Customer",
			customer_name="_Test Customer",
			transaction_date="2026-08-10",
			po_no=None,
			terms=None,
			base_grand_total=250,
			taxes=[],
			items=[
				frappe._dict(
					item_code="_Test Item",
					uom="Nos",
					stock_uom="Nos",
					qty=2,
					base_net_rate=125,
					base_net_amount=250,
					warehouse="Stores - TC",
					delivery_date="2026-08-20",
				)
			],
		)

		voucher = _sales_order_voucher(order, "TC", "Sales")

		self.assertEqual(voucher["metadata"]["type"], "Voucher")
		self.assertEqual(voucher["vouchertypename"], "Sales Order")
		self.assertEqual(voucher["date"], "20260810")
		self.assertEqual(voucher["ledgerentries"][0]["amount"], "-250.00")
		allocation = voucher["allinventoryentries"][0]["batchallocations"][0]
		self.assertEqual(allocation["orderno"], "SAL-ORD-TEST-1")
		self.assertEqual(allocation["godownname"], "Stores")
		self.assertEqual(allocation["orderduedate"], "20-Aug-2026")

	def test_tally_quantity_and_date_format(self):
		self.assertEqual(_quantity(2.5, "Box"), "2.5 Box")
		self.assertEqual(_tally_date("2026-08-10"), "20260810")
