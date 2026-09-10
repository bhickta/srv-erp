import frappe
from frappe.model.document import Document


class DynamicItemRequestUOM(Document):
	pass


def on_doctype_update():
	frappe.db.add_index(
		"Dynamic Item Request UOM",
		["parent", "uom"],
		"dynamic_item_request_uom_idx",
	)
