import frappe
from frappe import _
from frappe.utils import flt


CUSTOM_DISCOUNT_FIELD = "srv_discount_percentage"
RATE_BEFORE_DISCOUNT_FIELD = "srv_rate_before_discount"
LAST_DISCOUNT_FIELD = "srv_last_discount_percentage"


def validate_sales_order_discounts(doc, method=None):
	if doc.doctype != "Sales Order":
		return

	for row in doc.get("items") or []:
		validate_discount_percentage(row)

	if apply_sales_order_rate_discounts(doc):
		doc.calculate_taxes_and_totals()


def validate_discount_percentage(row):
	discount_percentage = flt(row.get(CUSTOM_DISCOUNT_FIELD))
	if discount_percentage < 0 or discount_percentage > 100:
		frappe.throw(
			_("Row {0}: Discount (%) on Rate must be between 0 and 100.").format(row.idx),
			frappe.ValidationError,
		)


def apply_sales_order_rate_discounts(doc):
	applied = False
	for row in doc.get("items") or []:
		applied = apply_sales_order_rate_discount(row) or applied
	return applied


def apply_sales_order_rate_discount(row):
	discount_percentage = flt(row.get(CUSTOM_DISCOUNT_FIELD))
	rate_precision = get_rate_precision(row)
	rate = flt(row.get("rate"), rate_precision)
	base_rate = flt(
		row.get(RATE_BEFORE_DISCOUNT_FIELD),
		rate_precision,
	)
	last_discount_percentage = flt(row.get(LAST_DISCOUNT_FIELD))

	if discount_percentage:
		if not base_rate or not is_previous_discounted_rate(row, rate, base_rate, last_discount_percentage):
			base_rate = rate

		set_row_value(row, RATE_BEFORE_DISCOUNT_FIELD, base_rate)
		set_row_value(
			row,
			"rate",
			flt(base_rate * (1 - discount_percentage / 100), rate_precision),
		)
		set_row_value(row, LAST_DISCOUNT_FIELD, discount_percentage)
		return True

	if base_rate and last_discount_percentage and is_previous_discounted_rate(
		row, rate, base_rate, last_discount_percentage
	):
		set_row_value(row, "rate", base_rate)
		set_row_value(row, RATE_BEFORE_DISCOUNT_FIELD, 0)
		set_row_value(row, LAST_DISCOUNT_FIELD, 0)
		return True

	if base_rate or last_discount_percentage:
		set_row_value(row, RATE_BEFORE_DISCOUNT_FIELD, 0)
		set_row_value(row, LAST_DISCOUNT_FIELD, 0)
		return True

	return False


def get_rate_precision(row):
	return row.precision("rate") if hasattr(row, "precision") else None


def set_row_value(row, fieldname, value):
	if hasattr(row, "set"):
		row.set(fieldname, value)
	else:
		row[fieldname] = value


def is_previous_discounted_rate(row, rate, base_rate, discount_percentage):
	if not discount_percentage:
		return False

	precision = get_rate_precision(row)
	previous_discounted_rate = flt(
		base_rate * (1 - discount_percentage / 100),
		precision,
	)
	return abs(flt(rate, precision) - previous_discounted_rate) <= 0.000001


def create_sales_order_item_rate_discount_custom_fields():
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields(
		{
			"Sales Order Item": [
				{
					"columns": 1,
					"fieldname": CUSTOM_DISCOUNT_FIELD,
					"fieldtype": "Percent",
					"in_list_view": 1,
					"insert_after": "rate",
					"label": "Discount (%) on Rate",
				},
				{
					"fieldname": RATE_BEFORE_DISCOUNT_FIELD,
					"fieldtype": "Currency",
					"hidden": 1,
					"insert_after": CUSTOM_DISCOUNT_FIELD,
					"label": "Rate Before SRV Discount",
					"no_copy": 1,
				},
				{
					"fieldname": LAST_DISCOUNT_FIELD,
					"fieldtype": "Percent",
					"hidden": 1,
					"insert_after": RATE_BEFORE_DISCOUNT_FIELD,
					"label": "Last SRV Discount (%)",
					"no_copy": 1,
				},
			]
		},
		update=True,
	)


def delete_property_setter(doctype, fieldname, property_name):
	property_setter = frappe.db.exists(
		"Property Setter",
		{
			"doc_type": doctype,
			"field_name": fieldname,
			"property": property_name,
		},
	)
	if property_setter:
		frappe.delete_doc("Property Setter", property_setter, ignore_permissions=True)


def clear_standard_discount_grid_overrides():
	for fieldname in ("discount_percentage", "discount_amount"):
		for property_name in ("columns", "in_list_view"):
			delete_property_setter("Sales Order Item", fieldname, property_name)


def set_sales_order_item_discount_grid_columns():
	create_sales_order_item_rate_discount_custom_fields()
	clear_standard_discount_grid_overrides()

	field_properties = {
		"item_code": {"columns": 2, "in_list_view": 1},
		CUSTOM_DISCOUNT_FIELD: {"columns": 1, "in_list_view": 1},
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


def migrate_existing_rate_discounts():
	create_sales_order_item_rate_discount_custom_fields()
	clear_standard_discount_grid_overrides()
