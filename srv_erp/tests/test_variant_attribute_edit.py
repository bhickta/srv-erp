from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from srv_erp.item.variant_attribute_edit import EditableVariantItem, sync_variant_signature


class TestVariantAttributeEdit(TestCase):
	def make_item(self):
		item = object.__new__(EditableVariantItem)
		item.variant_of = "TEMPLATE"
		item.variant_based_on = "Item Attribute"
		item.has_variants = 0
		item.name = "VARIANT"
		item.attributes = [SimpleNamespace(attribute="Size", attribute_value="12")]
		item.get_doc_before_save = MagicMock(
			return_value=SimpleNamespace(
				variant_of="TEMPLATE",
				has_variants=0,
				attributes=[SimpleNamespace(attribute="Size", attribute_value="10")],
			)
		)
		item.is_new = MagicMock(return_value=False)
		item.is_child_table_same = MagicMock(return_value=False)
		return item

	@patch("srv_erp.item.variant_attribute_edit.Item.validate_stock_exists_for_template_item")
	def test_existing_variant_can_change_values_after_stock(self, parent):
		item = self.make_item()
		item.stock_ledger_created = MagicMock(return_value=True)
		item.validate_stock_exists_for_template_item()
		parent.assert_not_called()

	@patch("srv_erp.item.variant_attribute_edit.Item.validate_stock_exists_for_template_item")
	def test_changing_template_retains_stock_guard(self, parent):
		item = self.make_item()
		item.variant_of = "OTHER"
		item.validate_stock_exists_for_template_item()
		parent.assert_called_once()

	@patch("srv_erp.item.variant_attribute_edit.Item.validate_variant_attributes")
	@patch("srv_erp.item.variant_attribute_edit.validate_item_variant_attributes")
	@patch("srv_erp.item.variant_attribute_edit.get_variant", return_value=None)
	def test_edited_values_are_validated_and_checked_for_duplicates(self, lookup, validate, parent):
		item = self.make_item()
		item.validate_variant_attributes()
		validate.assert_called_once_with(item, {"Size": "12"})
		lookup.assert_called_once_with("TEMPLATE", {"Size": "12"}, "VARIANT")

	@patch("srv_erp.item.variant_attribute_edit.Item.validate_variant_attributes")
	@patch("srv_erp.item.variant_attribute_edit.validate_item_variant_attributes")
	@patch("srv_erp.item.variant_attribute_edit.get_variant", return_value="DUPLICATE")
	@patch("srv_erp.item.variant_attribute_edit._", side_effect=lambda message: message)
	@patch("srv_erp.item.variant_attribute_edit.frappe.throw", side_effect=ValueError)
	def test_duplicate_combination_is_rejected(self, throw, translate, lookup, validate, parent):
		with self.assertRaises(ValueError):
			self.make_item().validate_variant_attributes()
		self.assertIn("DUPLICATE", throw.call_args.args[0])

	@patch("srv_erp.item.variant_attribute_edit.Item.validate_variant_attributes")
	@patch("srv_erp.item.variant_attribute_edit._", side_effect=lambda message: message)
	@patch("srv_erp.item.variant_attribute_edit.frappe.throw", side_effect=ValueError)
	def test_removing_attributes_is_rejected(self, throw, translate, parent):
		item = self.make_item()
		item.attributes = []
		with self.assertRaises(ValueError):
			item.validate_variant_attributes()

	@patch("srv_erp.item.variant_attribute_edit.Item.validate_variant_attributes")
	@patch("srv_erp.item.variant_attribute_edit.validate_item_variant_attributes")
	@patch("srv_erp.item.variant_attribute_edit.get_variant", return_value=None)
	def test_adding_attribute_validates_combination_and_sets_template(self, lookup, validate, parent):
		item = self.make_item()
		item.attributes.append(SimpleNamespace(attribute="Color", attribute_value="Red"))
		item.validate_variant_attributes()
		args = {"Size": "12", "Color": "Red"}
		validate.assert_called_once_with(item, args)
		lookup.assert_called_once_with("TEMPLATE", args, "VARIANT")
		self.assertTrue(all(row.variant_of == "TEMPLATE" for row in item.attributes))

	def test_signature_tracks_edited_values(self):
		item = self.make_item()
		item.dynamic_variant_signature = "old-signature"
		sync_variant_signature(item)
		self.assertNotEqual(item.dynamic_variant_signature, "old-signature")
		self.assertEqual(len(item.dynamic_variant_signature), 64)
