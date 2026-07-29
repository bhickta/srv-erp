import frappe
from frappe import _
from frappe.utils import flt


def validate_sales_order_discounts(doc, method=None):
	if doc.doctype != "Sales Order":
		return

	for row in doc.get("items") or []:
		validate_discount_percentage(row)
		validate_discount_amount(row)


def validate_discount_percentage(row):
	discount_percentage = flt(row.get("discount_percentage"))
	if discount_percentage < 0 or discount_percentage > 100:
		frappe.throw(
			_("Row {0}: Discount (%) must be between 0 and 100.").format(row.idx),
			frappe.ValidationError,
		)


def validate_discount_amount(row):
	discount_amount = flt(row.get("discount_amount"))
	if discount_amount < 0:
		frappe.throw(
			_("Row {0}: Discount Amount cannot be negative.").format(row.idx),
			frappe.ValidationError,
		)

	rate_with_margin = flt(row.get("rate_with_margin")) or flt(row.get("price_list_rate"))
	if rate_with_margin and discount_amount > rate_with_margin:
		frappe.throw(
			_("Row {0}: Discount Amount cannot be greater than item rate.").format(row.idx),
			frappe.ValidationError,
		)


def set_sales_order_item_discount_grid_columns():
	field_properties = {
		"item_code": {"columns": 2, "in_list_view": 1},
		"discount_percentage": {"columns": 1, "in_list_view": 1},
	}

	for fieldname, properties in field_properties.items():
		for property_name, value in properties.items():
			frappe.make_property_setter(
				{
					"doctype": "Sales Order Item",
					"doctype_or_field": "DocField",
					"fieldname": fieldname,
					"property": property_name,
					"value": value,
					"property_type": "Int",
				}
			)
