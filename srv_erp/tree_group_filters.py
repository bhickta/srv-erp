import frappe
from frappe.utils import cint


# Add future tree-backed list filters here.
TREE_GROUP_LIST_FILTERS = (
	{
		"doctype": "Sales Order",
		"fieldname": "customer_group",
		"label": "Tour",
	},
	{
		"doctype": "Delivery Note",
		"fieldname": "customer_group",
		"label": "Tour",
	},
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
				cint(current_value) == value
				if property_type == "Check"
				else current_value == value
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
		frappe.clear_cache(doctype=doctype)
		frappe.db.updatedb(doctype)


def validate_tree_link_field(meta, fieldname):
	field = meta.get_field(fieldname)

	if not field or field.fieldtype != "Link" or not field.options:
		frappe.throw(f"{meta.name}.{fieldname} must be a Link field")

	if not frappe.get_meta(field.options).is_tree:
		frappe.throw(
			f"{meta.name}.{fieldname} must link to a tree DocType"
		)

	return field


@frappe.whitelist()
def get_tree_group_descendants(doctype, fieldname, names):
	config = next(
		(
			item
			for item in TREE_GROUP_LIST_FILTERS
			if item["doctype"] == doctype
			and item["fieldname"] == fieldname
		),
		None,
	)

	if not config:
		frappe.throw("Invalid tree filter configuration")

	names = frappe.parse_json(names) if isinstance(names, str) else names

	if not names:
		return []

	if not isinstance(names, list):
		names = [names]

	names = list(
		dict.fromkeys(
			name
			for name in names
			if name
		)
	)

	if not names:
		return []

	parent_meta = frappe.get_meta(doctype)
	tree_field = parent_meta.get_field(fieldname)

	if not tree_field or tree_field.fieldtype != "Link":
		frappe.throw(
			f"{doctype}.{fieldname} must be a Link field"
		)

	tree_doctype = tree_field.options
	tree_meta = frappe.get_meta(tree_doctype)

	if not tree_meta.is_tree:
		frappe.throw(
			f"{tree_doctype} must be a tree DocType"
		)

	# Fetch the selected parent nodes.
	selected_nodes = frappe.get_all(
		tree_doctype,
		filters={
			"name": ["in", names],
		},
		fields=["name", "lft", "rgt"],
	)

	if not selected_nodes:
		return []

	tree = frappe.qb.DocType(tree_doctype)
	condition = None

	for node in selected_nodes:
		node_condition = (
			(tree.lft >= node.lft)
			& (tree.rgt <= node.rgt)
		)

		if condition is None:
			condition = node_condition
		else:
			condition = condition | node_condition

	query = (
		frappe.qb.from_(tree)
		.select(tree.name)
		.where(condition)
		.orderby(tree.lft)
	)

	rows = query.run()

	return [row[0] for row in rows]