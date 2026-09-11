import frappe
from erpnext.controllers.item_variant import (
	ItemVariantExistsError,
	get_variant,
	validate_item_variant_attributes,
)
from erpnext.stock.doctype.item.item import Item
from frappe import _
from frappe.utils import cint

from srv_erp.masters.dynamic_item.signatures import make_identity_signature


class EditableVariantItem(Item):
	def validate_stock_exists_for_template_item(self):
		previous = self.get_doc_before_save()
		if (
			previous
			and self.variant_of
			and self.variant_based_on == "Item Attribute"
			and previous.variant_of == self.variant_of
			and cint(previous.has_variants) == cint(self.has_variants)
		):
			return
		super().validate_stock_exists_for_template_item()

	def validate_variant_attributes(self):
		super().validate_variant_attributes()
		if self.is_new() or not self.variant_of or self.variant_based_on != "Item Attribute":
			return
		if self.is_child_table_same("attributes"):
			return
		previous = self.get_doc_before_save()
		if {row.attribute for row in self.attributes} != {row.attribute for row in previous.attributes}:
			frappe.throw(_("Only existing variant attribute values can be changed."))
		args = {row.attribute: row.attribute_value for row in self.attributes}
		if any(value is None or not str(value).strip() for value in args.values()):
			frappe.throw(_("A value is required for each variant attribute."))
		validate_item_variant_attributes(self, args)
		existing = get_variant(self.variant_of, args, self.name)
		if existing:
			frappe.throw(
				_("Item variant {0} exists with same attributes").format(existing), ItemVariantExistsError
			)


def sync_variant_signature(doc, method=None):
	if doc.variant_of and doc.get("dynamic_variant_signature") and not doc.is_child_table_same("attributes"):
		doc.dynamic_variant_signature = make_identity_signature(
			doc.variant_of, {row.attribute: row.attribute_value for row in doc.attributes}
		)
