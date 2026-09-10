import frappe
from frappe.model.document import Document


class DynamicItemRequestAttribute(Document):
	pass


def on_doctype_update():
	frappe.db.add_index(
		"Dynamic Item Request Attribute",
		["item_attribute", "attribute_value"],
		"dynamic_item_attribute_value_idx",
	)
