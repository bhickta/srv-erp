import frappe
from erpnext.stock.doctype.item.test_item import make_item
from erpnext.tests.utils import ERPNextTestSuite

from srv_erp.package_barcode.api import generate_package_barcodes, scan_package_barcode
from srv_erp.package_barcode.service import (
	DEFAULT_BARCODE_NAMING_SERIES,
	PackageBarcodeError,
	PackageBarcodeTransactionValidator,
	QTY_RULE_ALLOW_MANUAL,
	QTY_RULE_FORCE_BARCODE,
	get_item_uom_options,
)


class TestPackageBarcode(ERPNextTestSuite):
	def setUp(self):
		super().setUp()
		self.item = make_item(
			"_Test Package Barcode Item",
			properties={"is_stock_item": 1, "stock_uom": "Nos"},
			uoms=[{"uom": "Box", "conversion_factor": 10}],
		)
		frappe.db.set_single_value(
			"Barcode Settings", "package_barcode_naming_series", DEFAULT_BARCODE_NAMING_SERIES
		)
		frappe.db.set_single_value(
			"Barcode Settings", "package_barcode_default_qty_entry_rule", QTY_RULE_FORCE_BARCODE
		)
		frappe.db.set_value("Item", self.item.name, "package_barcode_qty_entry_rule", "Default")

	def test_generate_package_barcodes(self):
		result = generate_package_barcodes(self.item.name, "Nos", 2)

		self.assertEqual(result.generated_count, 2)
		self.assertEqual(
			frappe.db.count("Package Barcode", {"generation_batch": result.batch}),
			2,
		)

	def test_generate_package_barcodes_uses_configured_series(self):
		frappe.db.set_single_value("Barcode Settings", "package_barcode_naming_series", "TEST-PBC-.#####")

		result = generate_package_barcodes(self.item.name, "Nos", 1)

		self.assertTrue(result.barcodes[0].startswith("TEST-PBC-"))

	def test_scan_package_barcode(self):
		result = generate_package_barcodes(self.item.name, "Nos", 1)
		barcode = frappe.db.get_value("Package Barcode", result.barcodes[0], "barcode")

		scan_result = scan_package_barcode(barcode)

		self.assertEqual(scan_result["package_barcode"], result.barcodes[0])
		self.assertEqual(scan_result["barcode"], barcode)
		self.assertEqual(scan_result["item_code"], self.item.name)
		self.assertEqual(scan_result["uom"], "Nos")
		self.assertEqual(scan_result["qty"], 1)

	def test_item_uom_options_include_stock_uom(self):
		self.assertIn("Nos", get_item_uom_options(self.item.name))

	def test_duplicate_package_scan_rejected_in_same_document(self):
		result = generate_package_barcodes(self.item.name, "Nos", 1)
		barcode = frappe.db.get_value("Package Barcode", result.barcodes[0], "barcode")
		doc = frappe._dict(
			{
				"doctype": "Stock Entry",
				"package_barcodes": [
					frappe._dict(
						{
							"idx": 1,
							"package_barcode": result.barcodes[0],
							"barcode": barcode,
							"item_code": self.item.name,
							"uom": "Nos",
						}
					),
					frappe._dict(
						{
							"idx": 2,
							"package_barcode": result.barcodes[0],
							"barcode": barcode,
							"item_code": self.item.name,
							"uom": "Nos",
						}
					),
				],
			}
		)

		with self.assertRaises(PackageBarcodeError):
			PackageBarcodeTransactionValidator(doc).validate()

	def test_forced_package_barcode_qty_rejects_manual_qty_mismatch(self):
		frappe.db.set_single_value(
			"Barcode Settings", "package_barcode_default_qty_entry_rule", QTY_RULE_FORCE_BARCODE
		)
		result = generate_package_barcodes(self.item.name, "Nos", 1)
		barcode = frappe.db.get_value("Package Barcode", result.barcodes[0], "barcode")
		doc = frappe._dict(
			{
				"doctype": "Delivery Note",
				"items": [
					frappe._dict({"idx": 1, "item_code": self.item.name, "qty": 2}),
				],
				"package_barcodes": [
					frappe._dict(
						{
							"idx": 1,
							"package_barcode": result.barcodes[0],
							"barcode": barcode,
							"item_code": self.item.name,
							"uom": "Nos",
						}
					),
				],
			}
		)

		with self.assertRaises(PackageBarcodeError):
			PackageBarcodeTransactionValidator(doc).validate()

	def test_item_can_allow_manual_qty_over_global_forced_rule(self):
		frappe.db.set_single_value(
			"Barcode Settings", "package_barcode_default_qty_entry_rule", QTY_RULE_FORCE_BARCODE
		)
		frappe.db.set_value("Item", self.item.name, "package_barcode_qty_entry_rule", QTY_RULE_ALLOW_MANUAL)
		result = generate_package_barcodes(self.item.name, "Nos", 1)
		barcode = frappe.db.get_value("Package Barcode", result.barcodes[0], "barcode")
		doc = frappe._dict(
			{
				"doctype": "Delivery Note",
				"items": [
					frappe._dict({"idx": 1, "item_code": self.item.name, "qty": 2}),
				],
				"package_barcodes": [
					frappe._dict(
						{
							"idx": 1,
							"package_barcode": result.barcodes[0],
							"barcode": barcode,
							"item_code": self.item.name,
							"uom": "Nos",
						}
					),
				],
			}
		)

		PackageBarcodeTransactionValidator(doc).validate()
