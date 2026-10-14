import frappe
from frappe import _
from frappe.utils import cint


def validate_no_pending_sales_order(doc, method=None):
	"""
	Prevent creation of a new Sales Order when the customer
	already has an active Sales Order that is not fully delivered.

	Cancelled Sales Orders are ignored.
	"""

	if not doc.is_new():
		return

	if not doc.customer:
		return

	pending_orders = frappe.get_all(
		"Sales Order",
		filters={
			"customer": doc.customer,
			"docstatus": 1,
			"delivery_status": ["!=", "Fully Delivered"],
		},
		fields=[
			"name",
			"transaction_date",
			"delivery_status",
			"grand_total",
		],
		order_by="transaction_date desc",
		limit=20,
	)

	if not pending_orders:
		return

	order_lines = []

	for order in pending_orders:
		order_lines.append(
			_(
				"{0} — {1} — {2}"
			).format(
				order.name,
				order.transaction_date,
				order.delivery_status,
			)
		)

	frappe.throw(
		_(
			"Cannot create a new Sales Order for <b>{0}</b> because "
			"the customer already has pending Sales Order(s)."
		).format(doc.customer)
		+
		"<br><br>"
		+
		"<br>".join(order_lines)
	)
 
 
@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_brand_filtered_items(
	doctype,
	txt,
	searchfield,
	start,
	page_len,
	filters=None,
):
	filters = frappe.parse_json(filters) if filters else {}
	brand = filters.get("brand")

	if not brand:
		return []

	conditions = [
		"iva.attribute = 'Brand'",
		"iva.attribute_value = %(brand)s",
		"i.disabled = 0",
	]

	if txt:
		conditions.append("""
			(
				i.name LIKE %(txt)s
				OR i.item_name LIKE %(txt)s
			)
		""")

	return frappe.db.sql(
		f"""
		SELECT DISTINCT
			i.name,
			i.item_name
		FROM `tabItem Variant Attribute` iva
		INNER JOIN `tabItem` i
			ON i.name = iva.parent
		WHERE {" AND ".join(conditions)}
		ORDER BY i.name
		LIMIT %(start)s, %(page_len)s
		""",
		{
			"brand": brand,
			"txt": f"%{txt}%",
			"start": cint(start),
			"page_len": cint(page_len),
		},
	) 
 
def _variant_picker_conditions(brand=None, template=None, attributes=None, exclude_attribute=None):
	"""Build parameterized conditions shared by the result list and its facets."""
	conditions = ["i.disabled = 0", "i.variant_of IS NOT NULL", "i.variant_of != ''"]
	params = {}
	if brand:
		conditions.append("""EXISTS (
			SELECT 1 FROM `tabItem Variant Attribute` brand_attribute
			WHERE brand_attribute.parent = i.name AND brand_attribute.parenttype = 'Item'
			AND brand_attribute.attribute = 'Brand'
			AND brand_attribute.attribute_value = %(brand)s
		)""")
		params["brand"] = brand
	if template:
		conditions.append("i.variant_of = %(template)s")
		params["template"] = template
	for index, (attribute, value) in enumerate((attributes or {}).items()):
		if attribute == exclude_attribute:
			continue
		conditions.append(f"""EXISTS (
			SELECT 1 FROM `tabItem Variant Attribute` selected_{index}
			WHERE selected_{index}.parent = i.name AND selected_{index}.parenttype = 'Item'
			AND selected_{index}.attribute = %(attribute_{index})s
			AND selected_{index}.attribute_value = %(value_{index})s
		)""")
		params[f"attribute_{index}"] = attribute
		params[f"value_{index}"] = value
	return " AND ".join(conditions), params


@frappe.whitelist()
def get_variant_picker_data(brand=None, template=None, attributes=None, search=None):
	"""Return available attribute values and matching variants for one Sales Order row."""
	if not frappe.has_permission("Item", "read"):
		frappe.throw(_("Not permitted to read Items"), frappe.PermissionError)

	attributes = frappe.parse_json(attributes) if attributes else {}
	if not isinstance(attributes, dict) or len(attributes) > 20:
		frappe.throw(_("Invalid variant filters"))
	attributes = {
		str(attribute): str(value)
		for attribute, value in attributes.items()
		if attribute and value and attribute != "Brand"
	}
	if any(len(key) > 140 or len(value) > 140 for key, value in attributes.items()):
		frappe.throw(_("Invalid variant filters"))
	brand = str(brand or "")[:140]
	template = str(template or "")[:140]
	search = str(search or "")[:140]
	from srv_erp.masters.dynamic_item.configuration import is_grid_enabled, user_has_requester_role
	from srv_erp.masters.dynamic_item.profile_lookup import get_dynamic_variant_profile_name

	profile_name = get_dynamic_variant_profile_name(template) if template else None
	can_request = bool(
		profile_name and is_grid_enabled("Sales Order", "items") and user_has_requester_role()
	)

	base_where, base_params = _variant_picker_conditions(brand, template)
	attribute_rows = frappe.db.sql(
		f"""SELECT DISTINCT iva.attribute
		FROM `tabItem` i
		JOIN `tabItem Variant Attribute` iva ON iva.parent = i.name AND iva.parenttype = 'Item'
		WHERE {base_where} AND iva.attribute != 'Brand'
		ORDER BY iva.attribute LIMIT 20""",
		base_params,
		as_dict=True,
	)
	facets = []
	for row in attribute_rows:
		attribute = row.attribute
		where, params = _variant_picker_conditions(brand, template, attributes, attribute)
		params["facet_attribute"] = attribute
		values = frappe.db.sql(
			f"""SELECT DISTINCT iva.attribute_value
			FROM `tabItem` i
			JOIN `tabItem Variant Attribute` iva ON iva.parent = i.name AND iva.parenttype = 'Item'
			WHERE {where} AND iva.attribute = %(facet_attribute)s
			ORDER BY iva.attribute_value LIMIT 100""",
			params,
			as_dict=True,
		)
		facets.append({"attribute": attribute, "values": [value.attribute_value for value in values]})
	if can_request:
		from srv_erp.masters.dynamic_item.api import build_variant_options

		configured = build_variant_options(
			frappe.get_doc("Item", template),
			frappe.get_doc("Dynamic Variant Profile", profile_name),
			brand or None,
		)
		if not configured["requires_brand_selection"]:
			by_attribute = {facet["attribute"]: facet for facet in facets}
			for option in configured["attributes"]:
				attribute = option["attribute"]
				if attribute == "Brand" or option["numeric_values"]:
					continue
				facet = by_attribute.setdefault(attribute, {"attribute": attribute, "values": []})
				facet["values"] = list(dict.fromkeys([*facet["values"], *option["values"]]))
			facets = sorted(by_attribute.values(), key=lambda facet: facet["attribute"])

	where, params = _variant_picker_conditions(brand, template, attributes)
	if search:
		where += " AND (i.name LIKE %(search)s OR i.item_name LIKE %(search)s)"
		params["search"] = f"%{search}%"
	items = frappe.db.sql(
		f"""SELECT i.name, i.item_name, i.variant_of
		FROM `tabItem` i WHERE {where}
		ORDER BY i.item_name, i.name LIMIT 31""",
		params,
		as_dict=True,
	)
	return {
		"facets": facets,
		"items": items[:30],
		"has_more": len(items) > 30,
		"can_request": can_request,
	}


@frappe.whitelist()
def validate_sales_order_item_brand(item_code, brand):
    if not item_code or not brand:
        return {
            "allowed": True,
            "reason": None,
        }

    variant_brand = frappe.db.get_value(
        "Item Variant Attribute",
        {
            "parent": item_code,
            "parenttype": "Item",
            "attribute": "Brand",
        },
        "attribute_value",
    )

    # Item has no Brand variant attribute.
    # Such items are allowed regardless of selected Brand.
    if not variant_brand:
        return {
            "allowed": True,
            "reason": None,
        }

    # Item is a Brand variant, so it must match selected Brand.
    if variant_brand == brand:
        return {
            "allowed": True,
            "reason": None,
        }

    return {
        "allowed": False,
        "reason": variant_brand,
    }
