import frappe
from frappe import _


def execute(filters=None):
	filters = frappe._dict(filters or {})
	db_filters = {
		field: filters.get(field)
		for field in ("brand", "template_item", "item_attribute", "conflict_type", "revision", "status")
		if filters.get(field) not in (None, "")
	}
	rows = frappe.get_all(
		"Brand Variant Rule Conflict",
		filters=db_filters,
		fields=[
			"brand",
			"revision",
			"status",
			"conflict_type",
			"template_item",
			"item_code",
			"item_attribute",
			"attribute_value",
			"details",
			"detected_on",
		],
		order_by="detected_on desc, brand asc, template_item asc, item_code asc",
	)
	return get_columns(), rows


def get_columns():
	return [
		{"label": _("Brand"), "fieldname": "brand", "fieldtype": "Link", "options": "Brand", "width": 130},
		{"label": _("Revision"), "fieldname": "revision", "fieldtype": "Int", "width": 75},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 90},
		{"label": _("Conflict Type"), "fieldname": "conflict_type", "fieldtype": "Data", "width": 190},
		{
			"label": _("Item Template"),
			"fieldname": "template_item",
			"fieldtype": "Link",
			"options": "Item",
			"width": 160,
		},
		{
			"label": _("Existing Variant"),
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "Item",
			"width": 170,
		},
		{
			"label": _("Item Attribute"),
			"fieldname": "item_attribute",
			"fieldtype": "Link",
			"options": "Item Attribute",
			"width": 130,
		},
		{"label": _("Attribute Value"), "fieldname": "attribute_value", "fieldtype": "Data", "width": 130},
		{"label": _("Details"), "fieldname": "details", "fieldtype": "Data", "width": 250},
		{"label": _("Detected On"), "fieldname": "detected_on", "fieldtype": "Datetime", "width": 150},
	]
