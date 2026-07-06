import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from srv_erp.package_barcode.service import DEFAULT_BARCODE_NAMING_SERIES, QTY_RULE_ALLOW_MANUAL


def after_install():
	create_package_barcode_custom_fields()
	set_package_barcode_settings_defaults()


def after_migrate():
	create_package_barcode_custom_fields()
	set_package_barcode_settings_defaults()


def create_package_barcode_custom_fields():
	custom_fields = {
		"Item": [
			{
				"fieldname": "package_barcode_section",
				"fieldtype": "Section Break",
				"insert_after": "barcodes",
				"label": "Package Barcode",
				"collapsible": 1,
			},
			{
				"default": "Default",
				"description": "Controls whether Stock Entry and Delivery Note quantity must come from Package Barcode scans. Default uses Package Barcode Settings.",
				"fieldname": "package_barcode_qty_entry_rule",
				"fieldtype": "Select",
				"insert_after": "package_barcode_section",
				"label": "Package Barcode Qty Entry Rule",
				"options": "Default\nAllow Manual Qty\nForce Barcode Only",
			},
		],
		("Stock Entry", "Delivery Note"): [
			{
				"fieldname": "package_barcodes_section",
				"fieldtype": "Section Break",
				"insert_after": "items",
				"label": "Package Barcodes",
				"collapsible": 1,
			},
			{
				"fieldname": "package_barcodes",
				"fieldtype": "Table",
				"insert_after": "package_barcodes_section",
				"label": "Package Barcodes",
				"options": "Package Barcode Scan",
				"read_only": 1,
				"allow_on_submit": 1,
			},
		]
	}
	create_custom_fields(custom_fields, update=True)


def set_package_barcode_settings_defaults():
	if not frappe.db.get_single_value("Barcode Settings", "package_barcode_naming_series"):
		frappe.db.set_single_value(
			"Barcode Settings", "package_barcode_naming_series", DEFAULT_BARCODE_NAMING_SERIES
		)
	if not frappe.db.get_single_value("Barcode Settings", "package_barcode_default_qty_entry_rule"):
		frappe.db.set_single_value(
			"Barcode Settings", "package_barcode_default_qty_entry_rule", QTY_RULE_ALLOW_MANUAL
		)
