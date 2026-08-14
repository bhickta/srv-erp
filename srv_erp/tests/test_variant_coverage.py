import frappe
from erpnext.controllers.item_variant import create_variant
from erpnext.stock.doctype.item.test_item import make_item
from erpnext.tests.utils import ERPNextTestSuite

from srv_erp.srv_erp.report.variant_coverage.variant_coverage import (
	create_missing_variants,
	execute,
)
from srv_erp.item.variant_auto_creation import (
	ensure_brand_attribute_value,
	get_item_attribute_variant_sync_status,
	handle_brand_update,
	sync_missing_brand_variants,
	sync_attribute_brand_values_to_master,
	validate_item_attribute_brand_source,
)


class TestVariantCoverage(ERPNextTestSuite):
	def setUp(self):
		super().setUp()
		frappe.db.set_single_value("Masters Settings", "enforce_variant_approval", 0)
		frappe.db.set_single_value("Masters Settings", "allow_bulk_variant_creation", 1)
		frappe.clear_document_cache("Masters Settings", "Masters Settings")
		self.brand_attribute = "_Test VC Brand"
		self.size_attribute = "_Test VC Size"
		self.template = "_Test VC Template"

		self._ensure_attribute(
			self.brand_attribute,
			[
				("_Test VC Brand A", "VCA"),
				("_Test VC Brand B", "VCB"),
			],
		)
		self._ensure_attribute(
			self.size_attribute,
			[
				("_Test VC Small", "S"),
				("_Test VC Large", "L"),
			],
		)
		self._ensure_template()

		self._delete_variant("_Test VC Template-VCA-S")
		self._delete_variant("_Test VC Template-VCA-L")
		self._delete_variant("_Test VC Template-VCB-S")
		self._delete_variant("_Test VC Template-VCB-L")
		self._delete_variant("_Test VC Template-VCC-S")
		self._delete_variant("_Test VC Template-VCC-L")
		self._delete_variant("_Test VC Template-VCD-S")
		self._delete_variant("_Test VC Template-VCD-L")
		self._delete_brand("_Test VC Brand A")
		self._delete_brand("_Test VC Brand B")
		self._delete_brand("_Test VC Brand C")
		self._delete_brand("_Test VC Brand D")

		variant = create_variant(
			self.template,
			{
				self.brand_attribute: "_Test VC Brand A",
				self.size_attribute: "_Test VC Small",
			},
		)
		variant.save()
		frappe.db.set_single_value("SRV Settings", "auto_create_variants_on_brand_update", 0)
		frappe.db.set_single_value("SRV Settings", "variant_auto_create_attribute", self.brand_attribute)
		frappe.db.set_single_value("SRV Settings", "variant_auto_create_use_template_image", 0)

	def test_report_shows_created_and_missing_variant_combinations(self):
		columns, rows = execute({"item_template": self.template, "variant_attribute": self.brand_attribute})

		self.assertTrue(columns)
		self.assertEqual(len(rows), 4)
		self.assertEqual(self._count_status(rows, "Created"), 1)
		self.assertEqual(self._count_status(rows, "Missing"), 3)

		created_row = next(row for row in rows if row["status"] == "Created")
		self.assertEqual(created_row["variant_item"], "_Test VC Template-VCA-S")

	def test_report_filters_by_attribute_value(self):
		_, rows = execute(
			{
				"item_template": self.template,
				"variant_attribute": self.brand_attribute,
				"attribute_value": "_Test VC Brand B",
			}
		)

		self.assertEqual(len(rows), 2)
		self.assertEqual({row["attribute_value"] for row in rows}, {"_Test VC Brand B"})
		self.assertEqual(self._count_status(rows, "Missing"), 2)

	def test_create_missing_variants_creates_only_filtered_missing_combinations(self):
		result = create_missing_variants(
			{
				"item_template": self.template,
				"variant_attribute": self.brand_attribute,
				"attribute_value": "_Test VC Brand B",
			}
		)

		self.assertEqual(result["created"], 2)
		self.assertTrue(frappe.db.exists("Item", "_Test VC Template-VCB-S"))
		self.assertTrue(frappe.db.exists("Item", "_Test VC Template-VCB-L"))
		self.assertFalse(frappe.db.exists("Item", "_Test VC Template-VCA-L"))

		repeated_result = create_missing_variants(
			{
				"item_template": self.template,
				"variant_attribute": self.brand_attribute,
				"attribute_value": "_Test VC Brand B",
			}
		)
		self.assertEqual(repeated_result["created"], 0)

	def test_brand_update_does_not_create_variants_when_setting_is_disabled(self):
		handle_brand_update(frappe._dict({"name": "_Test VC Brand C", "brand": "_Test VC Brand C"}))

		self.assertFalse(frappe.db.exists("Item", "_Test VC Template-VCC-S"))
		self.assertFalse(frappe.db.exists("Item", "_Test VC Template-VCC-L"))

	def test_brand_update_creates_missing_variants_when_setting_is_enabled(self):
		frappe.db.set_single_value("SRV Settings", "auto_create_variants_on_brand_update", 1)

		handle_brand_update(frappe._dict({"name": "_Test VC Brand C", "brand": "_Test VC Brand C"}))

		self.assertTrue(frappe.db.exists("Item", "_Test VC Template-VCC-S"))
		self.assertTrue(frappe.db.exists("Item", "_Test VC Template-VCC-L"))

	def test_brand_filtered_sync_creates_only_selected_brand_variants(self):
		frappe.db.set_single_value("SRV Settings", "auto_create_variants_on_brand_update", 1)
		ensure_brand_attribute_value("_Test VC Brand C")
		ensure_brand_attribute_value("_Test VC Brand D")

		result = sync_missing_brand_variants(attribute_value="_Test VC Brand C")

		self.assertEqual(result["created"], 2)
		self.assertTrue(frappe.db.exists("Item", "_Test VC Template-VCC-S"))
		self.assertTrue(frappe.db.exists("Item", "_Test VC Template-VCC-L"))
		self.assertFalse(frappe.db.exists("Item", "_Test VC Template-VCD-S"))
		self.assertFalse(frappe.db.exists("Item", "_Test VC Template-VCD-L"))

	def test_attribute_sync_status_reports_missing_variants_when_auto_is_disabled(self):
		ensure_brand_attribute_value("_Test VC Brand C")

		status = get_item_attribute_variant_sync_status(self.brand_attribute)

		self.assertEqual(status["applicable"], 1)
		self.assertEqual(status["auto_create_enabled"], 0)
		self.assertEqual(status["missing_count"], 5)

	def test_brand_master_adds_item_attribute_value(self):
		frappe.get_doc(
			{
				"doctype": "Brand",
				"brand": "_Test VC Brand D",
				"brand_abbreviation": "VCD",
			}
		).insert(ignore_permissions=True)

		result = ensure_brand_attribute_value("_Test VC Brand D")

		self.assertEqual(result["created"], 1)
		self.assertTrue(
			frappe.db.exists(
				"Item Attribute Value",
				{"parent": self.brand_attribute, "attribute_value": "_Test VC Brand D"},
			)
		)
		self.assertEqual(
			frappe.db.get_value(
				"Item Attribute Value",
				{"parent": self.brand_attribute, "attribute_value": "_Test VC Brand D"},
				"abbr",
			),
			"VCD",
		)

	def test_conflicting_brand_abbreviation_does_not_block_sync(self):
		frappe.get_doc(
			{
				"doctype": "Brand",
				"brand": "_Test VC Brand D",
				"brand_abbreviation": "VCA",
			}
		).insert(ignore_permissions=True)

		result = ensure_brand_attribute_value("_Test VC Brand D")

		self.assertEqual(result["created"], 1)
		self.assertEqual(result["conflict"], 1)
		self.assertNotEqual(
			frappe.db.get_value(
				"Item Attribute Value",
				{"parent": self.brand_attribute, "attribute_value": "_Test VC Brand D"},
				"abbr",
			),
			"VCA",
		)

	def test_brand_attribute_values_create_brand_masters(self):
		frappe.delete_doc_if_exists("Brand", "_Test VC Brand A", force=1)
		frappe.delete_doc_if_exists("Brand", "_Test VC Brand B", force=1)

		result = sync_attribute_brand_values_to_master()

		self.assertEqual(result["created"], 2)
		self.assertTrue(frappe.db.exists("Brand", "_Test VC Brand A"))
		self.assertTrue(frappe.db.exists("Brand", "_Test VC Brand B"))
		self.assertEqual(
			frappe.db.get_value("Brand", "_Test VC Brand A", "brand_abbreviation"),
			"VCA",
		)
		self.assertEqual(
			frappe.db.get_value("Brand", "_Test VC Brand B", "brand_abbreviation"),
			"VCB",
		)

	def test_direct_brand_attribute_value_change_is_blocked(self):
		attribute = frappe.get_doc("Item Attribute", self.brand_attribute)
		attribute.append("item_attribute_values", {"attribute_value": "_Test VC Brand E", "abbr": "VCE"})

		with self.assertRaises(frappe.ValidationError):
			validate_item_attribute_brand_source(attribute)

	def _ensure_template(self):
		if frappe.db.exists("Item", self.template):
			return frappe.get_doc("Item", self.template)

		return make_item(
			self.template,
			properties={
				"has_variants": 1,
				"variant_based_on": "Item Attribute",
				"attributes": [
					{"attribute": self.brand_attribute},
					{"attribute": self.size_attribute},
				],
			},
		)

	def _ensure_attribute(self, attribute, values):
		if frappe.db.exists("Item Attribute", attribute):
			return

		doc = frappe.get_doc({"doctype": "Item Attribute", "attribute_name": attribute})
		for value, abbr in values:
			doc.append("item_attribute_values", {"attribute_value": value, "abbr": abbr})
		doc.save()

	def _add_attribute_value(self, value, abbr):
		doc = frappe.get_doc("Item Attribute", self.brand_attribute)
		if value not in {row.attribute_value for row in doc.item_attribute_values}:
			doc.append("item_attribute_values", {"attribute_value": value, "abbr": abbr})
			doc.save()

		return doc

	def _delete_variant(self, item_code):
		if frappe.db.exists("Item", item_code):
			frappe.delete_doc("Item", item_code, force=1)

	def _delete_brand(self, brand):
		if frappe.db.exists("Brand", brand):
			frappe.delete_doc("Brand", brand, force=1)

	@staticmethod
	def _count_status(rows, status):
		return len([row for row in rows if row["status"] == status])
