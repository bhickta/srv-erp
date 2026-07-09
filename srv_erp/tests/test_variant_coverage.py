import frappe
from erpnext.controllers.item_variant import create_variant
from erpnext.stock.doctype.item.test_item import make_item
from erpnext.tests.utils import ERPNextTestSuite

from srv_erp.srv_erp.report.variant_coverage.variant_coverage import (
	create_missing_variants,
	execute,
)


class TestVariantCoverage(ERPNextTestSuite):
	def setUp(self):
		super().setUp()
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

		variant = create_variant(
			self.template,
			{
				self.brand_attribute: "_Test VC Brand A",
				self.size_attribute: "_Test VC Small",
			},
		)
		variant.save()

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

	def _delete_variant(self, item_code):
		if frappe.db.exists("Item", item_code):
			frappe.delete_doc("Item", item_code, force=1)

	@staticmethod
	def _count_status(rows, status):
		return len([row for row in rows if row["status"] == status])
