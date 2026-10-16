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