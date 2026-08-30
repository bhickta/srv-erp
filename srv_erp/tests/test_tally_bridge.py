import json
import threading
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import replace
from unittest import TestCase
from unittest.mock import Mock

from srv_erp.tally_bridge.config import BridgeConfig
from srv_erp.tally_bridge.json_gateway import (
	build_master_imports,
	build_voucher_import,
	parse_import_response,
)
from srv_erp.tally_bridge.http_server import BridgeHTTPServer
from srv_erp.tally_bridge.service import SyncService, SyncSummary
from srv_erp.tally_bridge.xml_gateway import ImportResult as XMLImportResult
from srv_erp.tally_bridge.xml_gateway import build_voucher_import as build_xml_voucher_import


def sample_order():
	return {
		"source_doctype": "Sales Order",
		"name": "SAL-ORD-2026-00001",
		"modified": "2026-08-28 12:00:00",
		"source_hash": "hash-1",
		"operation": "Create",
		"transaction_date": "2026-08-28",
		"delivery_date": "2026-09-05",
		"customer": {"id": "CUST-1", "name": "Customer One", "gstin": "", "country": "India"},
		"currency": "INR",
		"reference": "PO-1",
		"narration": "Test order",
		"net_total": 250,
		"grand_total": 295,
		"rounding_adjustment": 0,
		"sales_ledger": "Sales",
		"round_off_ledger": "Round Off",
		"taxes": [{"ledger": "Output IGST", "amount": 45}],
		"items": [
			{
				"item_code": "ITEM-1",
				"item_name": "Item One",
				"description": "Item One",
				"item_group": "Products",
				"hsn_code": "1234",
				"stock_uom": "Nos",
				"stock_qty": 2,
				"rate": 125,
				"amount": 250,
				"warehouse": "Stores",
				"delivery_date": "2026-09-05",
			}
		],
		"masters": {
			"item_groups": [{"name": "Products", "parent": ""}],
			"units": ["Nos"],
			"warehouses": ["Stores"],
		},
	}


class TestTallyJSONGateway(TestCase):
	def test_master_imports_are_split_by_dependency(self):
		requests = build_master_imports(sample_order(), "Test Company")

		self.assertEqual(len(requests), 3)
		unit = requests[0]["tallymessage"][0]
		self.assertEqual(unit["metadata"]["type"], "Unit")
		self.assertEqual(unit["metadata"]["action"], "create")
		self.assertEqual(unit["originalname"], "Numbers")
		self.assertEqual(requests[1]["tallymessage"][-1]["metadata"]["type"], "Ledger")
		self.assertEqual(requests[2]["tallymessage"][0]["metadata"]["type"], "Stock Item")

	def test_voucher_contains_balanced_order_and_inventory_details(self):
		request = build_voucher_import(sample_order(), "Test Company", "target-1")
		voucher = request["tallymessage"][0]

		self.assertEqual(voucher["metadata"]["action"], "create")
		self.assertEqual(voucher["metadata"]["vchtype"], "Sales")
		self.assertEqual(voucher["vouchertypename"], "Sales")
		self.assertTrue(voucher["isinvoice"])
		self.assertFalse(voucher["isorder"])
		self.assertEqual(voucher["date"], "20260828")
		self.assertEqual(voucher["ledgerentries"][0]["amount"], "-295.00")
		inventory = voucher["allinventoryentries"][0]
		self.assertEqual(inventory["actualqty"], " 2 Nos")
		self.assertEqual(inventory["rate"], "125.00/Nos")
		bill = voucher["ledgerentries"][0]["billallocations"][0]
		self.assertEqual(bill["name"], sample_order()["name"])
		self.assertEqual(bill["billtype"], "New Ref")
		self.assertNotIn("orderno", inventory["batchallocations"][0])

	def test_source_doctype_is_part_of_the_tally_identity(self):
		sales_order = sample_order()
		delivery_note = dict(sales_order, source_doctype="Delivery Note")

		so_voucher = build_voucher_import(sales_order, "Test Company", "target-1")["tallymessage"][0]
		dn_voucher = build_voucher_import(delivery_note, "Test Company", "target-1")["tallymessage"][0]

		self.assertNotEqual(so_voucher["guid"], dn_voucher["guid"])
		self.assertEqual(so_voucher["vouchertypename"], "Sales")
		self.assertEqual(dn_voucher["vouchertypename"], "Sales")

	def test_import_exceptions_are_failures_even_when_status_is_one(self):
		result = parse_import_response(
			{
				"status": "1",
				"data": {
					"import_result": {
						"line_errors": ["Unit does not exist"],
						"errors": 0,
						"exceptions": 1,
					}
				},
			}
		)

		self.assertFalse(result.success)
		self.assertEqual(result.message, "Unit does not exist")

	def test_duplicate_voucher_can_be_acknowledged_after_lost_response(self):
		result = parse_import_response(
			{
				"status": "1",
				"data": {"import_result": {"ignored": 1, "errors": 0, "exceptions": 0}},
			},
			require_change=True,
			allow_ignored=True,
		)

		self.assertTrue(result.success)


class TestTallyXMLVoucherGateway(TestCase):
	def test_sales_order_and_delivery_note_are_both_sales_vouchers(self):
		sales_order = sample_order()
		delivery_note = dict(sales_order, source_doctype="Delivery Note", name="DN-00001")

		so_root = ET.fromstring(build_xml_voucher_import(sales_order, "Test Company", "target-1"))
		dn_root = ET.fromstring(build_xml_voucher_import(delivery_note, "Test Company", "target-1"))
		so_voucher = so_root.find(".//VOUCHER")
		dn_voucher = dn_root.find(".//VOUCHER")

		self.assertEqual(so_voucher.attrib["VCHTYPE"], "Sales")
		self.assertEqual(dn_voucher.attrib["VCHTYPE"], "Sales")
		self.assertEqual(so_voucher.findtext("VOUCHERTYPENAME"), "Sales")
		self.assertEqual(dn_voucher.findtext("VOUCHERTYPENAME"), "Sales")
		self.assertEqual(so_voucher.findtext("ISORDER"), "No")
		self.assertEqual(dn_voucher.findtext("ISORDER"), "No")
		self.assertEqual(so_voucher.findtext("PERSISTEDVIEW"), "Accounting Voucher View")
		self.assertEqual(dn_voucher.findtext("ISINVOICE"), "No")
		self.assertNotEqual(so_voucher.attrib["REMOTEID"], dn_voucher.attrib["REMOTEID"])

	def test_zero_value_sales_voucher_contains_quantities_without_zero_allocations(self):
		order = sample_order()
		order.update(grand_total=0, net_total=0, taxes=[])
		order["items"][0].update(rate=0, amount=0)

		root = ET.fromstring(build_xml_voucher_import(order, "Test Company", "target-1"))
		voucher = root.find(".//VOUCHER")
		entries = voucher.findall("LEDGERENTRIES.LIST")
		inventory = entries[1].find("INVENTORYALLOCATIONS.LIST")

		self.assertEqual(entries[0].findtext("LEDGERNAME"), "Customer One")
		self.assertIsNone(entries[0].find("AMOUNT"))
		self.assertEqual(entries[1].findtext("LEDGERNAME"), "Sales")
		self.assertIsNone(entries[1].find("AMOUNT"))
		self.assertIsNone(inventory.find("RATE"))
		self.assertIsNone(inventory.find("AMOUNT"))
		self.assertEqual(inventory.findtext("ACTUALQTY"), "2 Nos")

	def test_alter_uses_the_acknowledged_tally_master_id(self):
		order = sample_order()
		order.update(operation="Alter", tally_voucher_id="42")

		root = ET.fromstring(build_xml_voucher_import(order, "Test Company", "target-1"))
		voucher = root.find(".//VOUCHER")

		self.assertEqual(voucher.attrib["ACTION"], "Alter")
		self.assertEqual(voucher.attrib["TAGNAME"], "MASTER ID")
		self.assertEqual(voucher.attrib["TAGVALUE"], "42")


class TestSyncService(TestCase):
	def setUp(self):
		self.config = BridgeConfig(
			frappe_url="https://erp.example.com",
			api_key="key",
			api_secret="secret",
			erpnext_company="ERP Company",
			target_id="target-1",
			tally_company="Tally Company",
		)

	def test_company_mismatch_stops_before_fetch(self):
		frappe_client = Mock()
		tally_client = Mock()
		tally_client.get_current_company.return_value = "Wrong Company"
		tally_client.get_logical_function.return_value = True
		service = SyncService(self.config, frappe_client, tally_client)

		result = service.sync_once()

		self.assertIn("company mismatch", result.error)
		frappe_client.get_unsynced_documents.assert_not_called()

	def test_success_is_acknowledged_only_after_all_imports(self):
		frappe_client = Mock()
		frappe_client.get_unsynced_documents.return_value = {
			"schema_version": 1,
			"documents": [sample_order()],
		}
		tally_client = Mock()
		tally_client.get_current_company.return_value = "Tally Company"
		tally_client.get_logical_function.return_value = True
		tally_client.import_json.return_value = XMLImportResult(success=True, altered=1)
		tally_client.import_xml.return_value = XMLImportResult(
			success=True, created=1, last_voucher_id="42"
		)
		service = SyncService(self.config, frappe_client, tally_client)

		result = service.sync_once()

		self.assertEqual(result.succeeded, 1)
		self.assertEqual(tally_client.import_json.call_count, 3)
		tally_client.import_xml.assert_called_once()
		acknowledgement = frappe_client.acknowledge.call_args.args[1][0]
		self.assertEqual(acknowledgement["status"], "Success")
		self.assertEqual(acknowledgement["tally_voucher_id"], "42")

	def test_educational_date_override_preserves_original_date_in_narration(self):
		frappe_client = Mock()
		frappe_client.get_unsynced_documents.return_value = {
			"schema_version": 1,
			"documents": [sample_order()],
		}
		tally_client = Mock()
		tally_client.get_current_company.return_value = "Tally Company"
		tally_client.get_logical_function.return_value = True
		tally_client.import_json.return_value = XMLImportResult(success=True, altered=1)
		tally_client.import_xml.return_value = XMLImportResult(
			success=True, created=1, last_voucher_id="43"
		)
		config = replace(self.config, voucher_date_override="2026-08-01")

		result = SyncService(config, frappe_client, tally_client).sync_once()

		self.assertEqual(result.succeeded, 1)
		voucher = ET.fromstring(tally_client.import_xml.call_args.args[0]).find(".//VOUCHER")
		self.assertEqual(voucher.findtext("DATE"), "20260801")
		self.assertIn("original date 2026-08-28", voucher.findtext("NARRATION"))


class TestBridgeHTTPServer(TestCase):
	def test_click_returns_before_background_sync_finishes(self):
		entered = threading.Event()
		release = threading.Event()
		service = Mock()

		def slow_sync(limit=None):
			entered.set()
			release.wait(2)
			return SyncSummary(fetched=1, succeeded=1)

		service.sync_once.side_effect = slow_sync
		server = BridgeHTTPServer(("127.0.0.1", 0), service)
		server_thread = threading.Thread(target=server.serve_forever, daemon=True)
		server_thread.start()
		base_url = f"http://127.0.0.1:{server.server_port}"
		try:
			with urllib.request.urlopen(f"{base_url}/sync", timeout=1) as response:
				payload = json.loads(response.read())
			self.assertEqual(response.status, 202)
			self.assertTrue(payload["started"])
			self.assertTrue(entered.wait(1))

			with urllib.request.urlopen(f"{base_url}/sync", timeout=1) as response:
				second_payload = json.loads(response.read())
			self.assertFalse(second_payload["started"])

			with urllib.request.urlopen(f"{base_url}/sync-status", timeout=1) as response:
				status = json.loads(response.read())
			self.assertTrue(status["running"])
		finally:
			release.set()
			server.shutdown()
			server.server_close()
			server_thread.join(2)
