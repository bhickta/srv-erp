from unittest import TestCase
from unittest.mock import MagicMock, patch

from srv_erp.item.variant_price_sync import (
	PRICE_FIELDS,
	_sync_source_to_variants,
	protect_managed_variant_price,
)


class TestVariantPriceSync(TestCase):
	@patch("srv_erp.item.variant_price_sync.frappe.get_all")
	@patch("srv_erp.item.variant_price_sync.frappe.new_doc")
	def test_sync_creates_one_managed_price_per_variant(self, new_doc, get_all):
		get_all.return_value = []
		created = []

		def make_price(_doctype):
			doc = MagicMock()
			doc.is_new.return_value = True
			doc.flags = frappe_flags = MagicMock()
			frappe_flags.variant_price_sync = False
			created.append(doc)
			return doc

		new_doc.side_effect = make_price
		source = MagicMock(name="source")
		source.name = "MASTER-PRICE"
		source.get.side_effect = lambda fieldname: {field: field for field in PRICE_FIELDS}.get(fieldname)

		_sync_source_to_variants(source, ["VARIANT-A", "VARIANT-B"])

		self.assertEqual(len(created), 2)
		self.assertEqual([doc.item_code for doc in created], ["VARIANT-A", "VARIANT-B"])
		for doc in created:
			self.assertEqual(doc.variant_price_template, source.name)
			doc.insert.assert_called_once()

	@patch("srv_erp.item.variant_price_sync.frappe.get_doc")
	@patch("srv_erp.item.variant_price_sync.frappe.get_all")
	def test_sync_adopts_matching_existing_price(self, get_all, get_doc):
		source = MagicMock()
		source.name = "MASTER-PRICE"
		source.price_list = "Selling"
		source.get.side_effect = lambda fieldname: {
			"price_list": "Selling",
			"uom": "Nos",
			"packing_unit": 0,
		}.get(fieldname)
		existing = AttrDict(
			name="OLD-PRICE",
			item_code="VARIANT-A",
			variant_price_template=None,
			price_list="Selling",
			uom="Nos",
			packing_unit=None,
		)
		get_all.return_value = [existing]
		managed_price = MagicMock()
		managed_price.flags = MagicMock()
		managed_price.is_new.return_value = False
		get_doc.return_value = managed_price

		_sync_source_to_variants(source, ["VARIANT-A"])

		get_doc.assert_called_once_with("Item Price", "OLD-PRICE")
		self.assertEqual(managed_price.variant_price_template, "MASTER-PRICE")
		managed_price.save.assert_called_once()

	@patch("srv_erp.item.variant_price_sync._", side_effect=lambda message: message)
	@patch("srv_erp.item.variant_price_sync.frappe.bold", side_effect=lambda value: value)
	@patch("srv_erp.item.variant_price_sync.frappe.throw")
	def test_managed_price_cannot_be_edited_directly(self, throw, _bold, _translate):
		doc = MagicMock()
		doc.get.side_effect = lambda fieldname: {
			"variant_price_template": "MASTER-PRICE",
		}.get(fieldname)
		doc.flags.get.return_value = False
		doc.get_doc_before_save.return_value = None

		protect_managed_variant_price(doc)

		throw.assert_called_once()


class AttrDict(dict):
	__getattr__ = dict.get
