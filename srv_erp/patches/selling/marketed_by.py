import frappe

from srv_erp.sales_order_attributes import create_sales_order_attribute_custom_fields


def convert_marketed_by_to_small_text():
	force_marketed_by_small_text_fields()
	create_sales_order_attribute_custom_fields()
	copy_custom_market_by_values()
	remove_custom_market_by_field()
	remove_marketed_by_doctype()


def force_marketed_by_small_text_fields():
	for doctype in ("Sales Order", "Sales Order Item"):
		field_name = f"{doctype}-marketed_by"
		if not frappe.db.exists("Custom Field", field_name):
			continue

		frappe.db.set_value(
			"Custom Field",
			field_name,
			{
				"fieldtype": "Small Text",
				"options": None,
			},
		)


def copy_custom_market_by_values():
	if not frappe.db.has_column("Sales Order", "custom_market_by"):
		return

	frappe.db.sql(
		"""
		update `tabSales Order`
		set marketed_by = custom_market_by
		where ifnull(marketed_by, '') = ''
			and ifnull(custom_market_by, '') != ''
		"""
	)


def remove_custom_market_by_field():
	field_name = "Sales Order-custom_market_by"
	if frappe.db.exists("Custom Field", field_name):
		frappe.delete_doc("Custom Field", field_name, ignore_permissions=True)


def remove_marketed_by_doctype():
	if frappe.db.exists("DocType", "Marketed By"):
		frappe.delete_doc("DocType", "Marketed By", ignore_permissions=True, force=True)
