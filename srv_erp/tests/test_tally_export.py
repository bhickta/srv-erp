import codecs
import json
from types import SimpleNamespace
from unittest import TestCase

import frappe

from srv_erp.integrations.tally_export import (
	MASTER_IMPORT_FORMAT_VARIABLE,
	SUPPORTED_MASTER_DOCTYPES,
	VOUCHER_IMPORT_FORMAT_VARIABLE,
	_clean_name,
	_encode_tally_json,
	_import_payload,
	_ledger,
	_parse_doctypes,
	_quantity,
	_sales_order_voucher,
	_tally_date,
	_tally_due_date,
)


class TestTallyExport(TestCase):
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
		self.assertEqual(
			set(SUPPORTED_MASTER_DOCTYPES),
			{
				"Account",
				"Customer",
				"Supplier",
				"Cost Center",
				"UOM",
				"Item Group",
				"Warehouse",
				"Item",
			},
		)

		with self.assertRaises(frappe.ValidationError):
			_parse_doctypes(json.dumps({"Account": True}))

	def test_sales_order_voucher_uses_tally_order_structure(self):
		order = SimpleNamespace(
			name="SAL-ORD-TEST-1",
			customer="_Test Customer",
			customer_name="_Test Customer",
			transaction_date="2026-08-10",
			po_no=None,
			terms=None,
			base_grand_total=250,
			taxes=[],
			items=[
				SimpleNamespace(
					item_code="_Test Item",
					uom="Box",
					stock_uom="Nos",
					qty=2,
					stock_qty=20,
					base_net_rate=125,
					base_net_amount=250,
					warehouse="Stores - TC",
					delivery_date="2026-08-20",
				)
			],
		)
		order.get = lambda key, default=None: getattr(order, key, default)

		voucher = _sales_order_voucher(order, "TC", "Sales")

		self.assertEqual(voucher["metadata"]["type"], "Voucher")
		self.assertEqual(voucher["vouchertypename"], "Sales Order")
		self.assertEqual(voucher["date"], "20260810")
		self.assertEqual(voucher["ledgerentries"][0]["amount"], "-250.00")
		inventory_entry = voucher["allinventoryentries"][0]
		self.assertEqual(inventory_entry["rate"], "12.50/Nos")
		self.assertEqual(inventory_entry["actualqty"], "20 Nos")
		allocation = inventory_entry["batchallocations"][0]
		self.assertEqual(allocation["orderno"], "SAL-ORD-TEST-1")
		self.assertEqual(allocation["godownname"], "Stores")
		self.assertEqual(allocation["actualqty"], "20 Nos")
		self.assertEqual(allocation["orderduedate"], "10 Days")

	def test_quantity_only_order_omits_zero_accounting_entries(self):
		order = SimpleNamespace(
			name="SAL-ORD-ZERO",
			customer="Customer",
			customer_name="Customer",
			transaction_date="2026-08-10",
			po_no=None,
			terms=None,
			base_grand_total=0,
			taxes=[],
			items=[
				SimpleNamespace(
					item_code="ITEM-1",
					uom="Box",
					stock_uom="Nos",
					qty=2,
					stock_qty=20,
					base_net_rate=0,
					base_net_amount=0,
					warehouse="Stores - TC",
					delivery_date="2026-08-20",
				)
			],
		)
		order.get = lambda key, default=None: getattr(order, key, default)

		voucher = _sales_order_voucher(order, "TC", "Sales")

		self.assertNotIn("ledgerentries", voucher)
		self.assertNotIn("accountingallocations", voucher["allinventoryentries"][0])

	def test_tally_quantity_and_date_format(self):
		self.assertEqual(_quantity(2.5, "Box"), "2.5 Box")
		self.assertEqual(_tally_date("2026-08-10"), "20260810")
		self.assertEqual(_tally_due_date("2026-08-10", "2026-08-10"), "0 Days")
		self.assertEqual(_tally_due_date("2026-08-11", "2026-08-10"), "1 Day")

	def test_release_7_import_context_and_utf16_encoding(self):
		master_payload = _import_payload("Tally Test Company", MASTER_IMPORT_FORMAT_VARIABLE, [])
		voucher_payload = _import_payload("Tally Test Company", VOUCHER_IMPORT_FORMAT_VARIABLE, [])

		self.assertEqual(
			master_payload["static_variables"],
			[
				{"name": "svMstImportFormat", "value": "jsonex"},
				{"name": "svCurrentCompany", "value": "Tally Test Company"},
			],
		)
		self.assertEqual(
			voucher_payload["static_variables"][0],
			{"name": "svVchImportFormat", "value": "jsonex"},
		)

		content = _encode_tally_json({"tallymessage": [{"name": "Café"}]})
		self.assertTrue(content.startswith(codecs.BOM_UTF16_LE))
		self.assertEqual(json.loads(content.decode("utf-16"))["tallymessage"][0]["name"], "Café")
