import frappe
from frappe.utils import cint


# Add future tree-backed list filters here. A Link field whose target is a tree
# DocType is rendered by Frappe with the "Descendants of (inclusive)" operator.
TREE_GROUP_LIST_FILTERS = (
	{"doctype": "Sales Order", "fieldname": "customer_group", "label": "Tour"},
	{"doctype": "Delivery Note", "fieldname": "customer_group", "label": "Tour"},
)

FILTER_FIELD_PROPERTIES = {
	"in_standard_filter": (1, "Check"),
	"search_index": (1, "Check"),
}


def configure_tree_group_list_filters(config=None):
	"""Expose indexed, tree-aware standard filters on configured DocTypes."""
	config = TREE_GROUP_LIST_FILTERS if config is None else config

	configured_doctypes = []
	for filter_config in config:
		doctype = filter_config["doctype"]
		fieldname = filter_config["fieldname"]
		meta = frappe.get_meta(doctype)
		field = validate_tree_link_field(meta, fieldname)
		properties = {
			**FILTER_FIELD_PROPERTIES,
			"label": (filter_config["label"], "Data"),
		}
		for property_name, (value, property_type) in properties.items():
			current_value = field.get(property_name)
			is_current_value = (
				cint(current_value) == value if property_type == "Check" else current_value == value
			)
			if is_current_value:
				continue
			frappe.make_property_setter(
				{
					"doctype": doctype,
					"doctype_or_field": "DocField",
					"fieldname": fieldname,
					"property": property_name,
					"value": value,
					"property_type": property_type,
				}
			)
		if doctype not in configured_doctypes:
			configured_doctypes.append(doctype)

	for doctype in configured_doctypes:
		# Refresh metadata before schema sync so search_index creates a database
		# index. updatedb is idempotent when the index already exists.
		frappe.clear_cache(doctype=doctype)
		frappe.db.updatedb(doctype)


def validate_tree_link_field(meta, fieldname):
	field = meta.get_field(fieldname)
	if not field or field.fieldtype != "Link" or not field.options:
		frappe.throw(f"{meta.name}.{fieldname} must be a Link field")

	if not frappe.get_meta(field.options).is_tree:
		frappe.throw(f"{meta.name}.{fieldname} must link to a tree DocType")

	return field
