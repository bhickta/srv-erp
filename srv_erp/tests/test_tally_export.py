import json

import frappe
from erpnext.tests.utils import ERPNextTestSuite

from srv_erp.integrations.tally_export import (
	SUPPORTED_MASTER_DOCTYPES,
	_clean_name,
	_ledger,
	_parse_doctypes,
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
