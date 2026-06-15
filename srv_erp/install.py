from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def after_install():
	create_package_barcode_custom_fields()


def after_migrate():
	create_package_barcode_custom_fields()


def create_package_barcode_custom_fields():
	custom_fields = {
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

