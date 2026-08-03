import frappe
from erpnext.controllers.item_variant import create_variant
from erpnext.stock.doctype.item.test_item import make_item
from erpnext.tests.utils import ERPNextTestSuite


class TestItemGroupSync(ERPNextTestSuite):
	def setUp(self):
		super().setUp()
		self.item_group_a = "_Test Variant Group A"
		self.item_group_b = "_Test Variant Group B"
		self.attribute = "_Test Variant Sync Size"
		self.template = "_Test Variant Sync Template"

		self.ensure_item_group(self.item_group_a)
		self.ensure_item_group(self.item_group_b)
		self.ensure_attribute()
		self.cleanup_items()

	def test_template_item_group_syncs_to_variant(self):
		template = self.make_template(self.item_group_a)
		variant = create_variant(template.name, {self.attribute: "_Test Variant Sync Small"})
		variant.save()

		template.item_group = self.item_group_b
		template.save()

		self.assertEqual(frappe.db.get_value("Item", variant.name, "item_group"), self.item_group_b)

	def test_template_item_field_syncs_to_variant(self):
		template = self.make_template(self.item_group_a)
		variant = create_variant(template.name, {self.attribute: "_Test Variant Sync Small"})
		variant.save()

		template = frappe.get_doc("Item", template.name)
		template.is_sales_item = 0
		template.save()

		self.assertEqual(frappe.db.get_value("Item", variant.name, "is_sales_item"), 0)

	def test_template_item_name_syncs_to_variant(self):
		template = self.make_template(self.item_group_a)
		variant = create_variant(template.name, {self.attribute: "_Test Variant Sync Small"})
		variant.save()

		template = frappe.get_doc("Item", template.name)
		template.item_name = "_Test Synced Template Name"
		template.save()

		self.assertEqual(
			frappe.db.get_value("Item", variant.name, "item_name"),
			"_Test Synced Template Name - _Test Variant Sync Small",
		)

	def test_new_variant_item_name_uses_template_and_attributes(self):
		template = self.make_template(self.item_group_a)
		template.item_name = "_Test Template Display Name"
		template.save()

		variant = create_variant(template.name, {self.attribute: "_Test Variant Sync Small"})
		variant.save()

		self.assertEqual(
			frappe.db.get_value("Item", variant.name, "item_name"),
			"_Test Template Display Name - _Test Variant Sync Small",
		)

	def test_variant_item_group_cannot_be_changed_directly(self):
		template = self.make_template(self.item_group_a)
		variant = create_variant(template.name, {self.attribute: "_Test Variant Sync Small"})
		variant.save()

		variant = frappe.get_doc("Item", variant.name)
		variant.item_group = self.item_group_b

		with self.assertRaises(frappe.ValidationError):
			variant.save()

	def test_variant_item_field_cannot_be_changed_directly(self):
		template = self.make_template(self.item_group_a)
		variant = create_variant(template.name, {self.attribute: "_Test Variant Sync Small"})
		variant.save()

		variant = frappe.get_doc("Item", variant.name)
		variant.is_sales_item = 0 if template.is_sales_item else 1

		with self.assertRaises(frappe.ValidationError):
			variant.save()

	def test_variant_item_name_cannot_be_changed_directly(self):
		template = self.make_template(self.item_group_a)
		variant = create_variant(template.name, {self.attribute: "_Test Variant Sync Small"})
		variant.save()

		variant = frappe.get_doc("Item", variant.name)
		variant.item_name = "_Test Direct Variant Name"

		with self.assertRaises(frappe.ValidationError):
			variant.save()

	def make_template(self, item_group):
		return make_item(
			self.template,
			properties={
				"has_variants": 1,
				"variant_based_on": "Item Attribute",
				"item_group": item_group,
				"is_sales_item": 1,
				"attributes": [{"attribute": self.attribute}],
			},
		)

	def ensure_item_group(self, item_group):
		if frappe.db.exists("Item Group", item_group):
			return

		frappe.get_doc(
			{
				"doctype": "Item Group",
				"item_group_name": item_group,
				"parent_item_group": "All Item Groups",
				"is_group": 0,
			}
		).insert()

	def ensure_attribute(self):
		if frappe.db.exists("Item Attribute", self.attribute):
			return

		doc = frappe.get_doc({"doctype": "Item Attribute", "attribute_name": self.attribute})
		doc.append(
			"item_attribute_values",
			{"attribute_value": "_Test Variant Sync Small", "abbr": "SVS"},
		)
		doc.save()

	def cleanup_items(self):
		for item in frappe.get_all("Item", filters={"variant_of": self.template}, pluck="name"):
			frappe.delete_doc("Item", item, force=1)
		frappe.delete_doc_if_exists("Item", self.template, force=1)
