import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from srv_erp.package_barcode.service import DEFAULT_BARCODE_NAMING_SERIES, QTY_RULE_ALLOW_MANUAL
from srv_erp.item.variant_auto_creation import (
	set_srv_settings_defaults,
	sync_brand_master_values_to_attribute,
)
from srv_erp.selling.sales_order_attributes import create_sales_order_attribute_custom_fields
from srv_erp.selling.sales_order_discount import set_sales_order_item_discount_grid_columns
from srv_erp.selling.sales_order_ui import (
	configure_sales_order_pending_qty_field,
	set_sales_order_ui_defaults,
)
from srv_erp.selling.sales_person_user_mapping import sync_all_sales_person_user_permissions
from srv_erp.stock.stock_balance_report import use_srv_stock_balance_report
from srv_erp.tree_group_filters import configure_tree_group_list_filters


def before_migrate():
	ensure_dsr_roles()


def after_install():
	ensure_dsr_roles()
	create_brand_custom_fields()
	create_variant_price_custom_fields()
	create_package_barcode_custom_fields()
	create_stock_reconciliation_package_uom_custom_fields()
	create_dsr_custom_fields()
	create_sales_order_attribute_custom_fields()
	create_stock_entry_detail_custom_fields()
	configure_tree_group_list_filters()
	set_sales_order_item_discount_grid_columns()
	set_sales_order_ui_defaults()
	configure_sales_order_pending_qty_field()
	sync_all_sales_person_user_permissions()
	use_srv_stock_balance_report()
	set_package_barcode_settings_defaults()
	set_srv_settings_defaults()
	sync_brand_master_values_to_attribute()


def after_migrate():
	ensure_dsr_roles()
	create_brand_custom_fields()
	create_variant_price_custom_fields()
	create_package_barcode_custom_fields()
	create_stock_reconciliation_package_uom_custom_fields()
	create_dsr_custom_fields()
	create_sales_order_attribute_custom_fields()
	create_stock_entry_detail_custom_fields()
	configure_tree_group_list_filters()
	set_sales_order_item_discount_grid_columns()
	set_sales_order_ui_defaults()
	configure_sales_order_pending_qty_field()
	sync_all_sales_person_user_permissions()
	use_srv_stock_balance_report()
	migrate_legacy_dsr_configuration()
	set_package_barcode_settings_defaults()
	set_srv_settings_defaults()
	sync_brand_master_values_to_attribute()


def create_brand_custom_fields():
	create_custom_fields(
		{
			"Brand": [
				{
					"description": "Used as the abbreviation for Brand values in Item Attribute variants. If blank, SRV ERP generates a unique abbreviation during sync.",
					"fieldname": "brand_abbreviation",
					"fieldtype": "Data",
					"insert_after": "brand",
					"in_list_view": 1,
					"label": "Brand Abbreviation",
				},
				{
					"default": "0",
					"description": "Disabled brands are excluded from new variant creation. Existing variants for disabled brands are disabled automatically.",
					"fieldname": "disabled",
					"fieldtype": "Check",
					"insert_after": "brand_abbreviation",
					"in_list_view": 1,
					"in_standard_filter": 1,
					"label": "Disabled",
				},
			],
		},
		update=True,
	)


def create_variant_price_custom_fields():
	create_custom_fields(
		{
			"Item Price": [
				{
					"default": "0",
					"description": "When checked, this price is the single source of truth for every variant of the selected template item.",
					"fieldname": "is_variant_price_template",
					"fieldtype": "Check",
					"hidden": 1,
					"insert_after": "item_code",
					"label": "Variant Price Template",
					"read_only": 1,
				},
				{
					"fieldname": "variant_price_template",
					"fieldtype": "Data",
					"hidden": 1,
					"insert_after": "is_variant_price_template",
					"label": "Variant Price Template ID",
					"read_only": 1,
				},
			],
		},
		update=True,
	)


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
				"description": "Controls whether Stock Entry, Delivery Note, and Stock Reconciliation quantity must come from Package Barcode scans. Default uses Package Barcode Settings.",
				"fieldname": "package_barcode_qty_entry_rule",
				"fieldtype": "Select",
				"insert_after": "package_barcode_section",
				"label": "Package Barcode Qty Entry Rule",
				"options": "Default\nAllow Manual Qty\nForce Barcode Only",
			},
		],
		("Stock Entry", "Delivery Note", "Stock Reconciliation"): [
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
		],
	}
	create_custom_fields(custom_fields, update=True)


def create_stock_entry_detail_custom_fields():
	create_custom_fields(
		{
			"Stock Entry Detail": [
				{
					"fieldname": "remarks",
					"fieldtype": "Small Text",
					"insert_after": "description",
					"label": "Remarks",
					"in_list_view": 1,
				}
			],
		},
		update=True,
	)


def create_dsr_custom_fields():
	create_custom_fields(
		{
			"Sales Person": [
				{
					"default": "9",
					"description": "Reimbursement rate per kilometer used when calculating DSR travel expense.",
					"fieldname": "travel_rate",
					"fieldtype": "Currency",
					"insert_after": "employee",
					"label": "Travel Rate",
					"non_negative": 1,
				},
			],
		},
		update=True,
	)


def ensure_dsr_roles():
	for role_name in ("Sales Rapl", "Auditor", "Payment Auditor"):
		if not frappe.db.exists("Role", role_name):
			frappe.get_doc(
				{
					"doctype": "Role",
					"role_name": role_name,
					"desk_access": 1,
				}
			).insert(ignore_permissions=True)


def migrate_legacy_dsr_configuration():
	"""Copy reusable DSRA masters and submission settings when the legacy app exists."""
	if frappe.db.exists("DocType", "Expense Type"):
		for expense_type in frappe.get_all(
			"Expense Type",
			fields=["name", "expense_name", "unit_of_expense", "rates"],
		):
			expense_name = expense_type.expense_name or expense_type.name
			if frappe.db.exists("DSR Expense Type", expense_name):
				continue
			frappe.get_doc(
				{
					"doctype": "DSR Expense Type",
					"expense_name": expense_name,
					"unit_of_expense": expense_type.unit_of_expense,
					"default_rate": expense_type.rates,
					"is_fuel": expense_name.lower() == "petrol",
				}
			).insert(ignore_permissions=True)

	if frappe.db.exists("DocType", "POI"):
		for poi in frappe.get_all(
			"POI",
			fields=["name", "po_office", "district", "state", "pincode", "latitude", "longitude"],
		):
			town_name = poi.po_office or poi.name
			if frappe.db.exists("DSR Town", town_name):
				continue
			frappe.get_doc(
				{
					"doctype": "DSR Town",
					"town_name": town_name,
					"district": poi.district,
					"state": poi.state,
					"pin_code": poi.pincode,
					"latitude": poi.latitude,
					"longitude": poi.longitude,
				}
			).insert(ignore_permissions=True)

	if not frappe.db.exists("DocType", "Raplbaddi Settings"):
		return
	if not frappe.get_meta("Raplbaddi Settings").has_field("submission_settings"):
		return

	target_settings = frappe.get_single("SRV Settings")
	if target_settings.get("dsr_submission_rules"):
		return

	legacy_settings = frappe.get_single("Raplbaddi Settings")
	for rule in legacy_settings.get("submission_settings") or []:
		if rule.document_type != "Daily Sales Report By Admin":
			continue
		target_settings.append(
			"dsr_submission_rules",
			{
				"document_type": "DSR",
				"tolerance": rule.tolerance,
				"unit": rule.unit,
			},
		)
		target_settings.save(ignore_permissions=True)
		break


def create_stock_reconciliation_package_uom_custom_fields():
	custom_fields = {
		"Stock Reconciliation Item": [
			{
				"fieldname": "package_uom_section",
				"fieldtype": "Section Break",
				"insert_after": "qty",
				"label": "Package UOM",
				"collapsible": 1,
			},
			{
				"fieldname": "package_qty",
				"fieldtype": "Float",
				"insert_after": "package_uom_section",
				"label": "Package Qty",
				"precision": "3",
				"read_only": 1,
			},
			{
				"fieldname": "package_uom",
				"fieldtype": "Link",
				"insert_after": "package_qty",
				"label": "Package UOM",
				"options": "UOM",
				"read_only": 1,
			},
			{
				"fieldname": "package_conversion_factor",
				"fieldtype": "Float",
				"insert_after": "package_uom",
				"label": "Package Conversion Factor",
				"precision": "9",
				"read_only": 1,
			},
		],
	}
	create_custom_fields(custom_fields, update=True)


def set_stock_reconciliation_package_uom_grid_columns():
	create_stock_reconciliation_package_uom_custom_fields()
	field_properties = {
		"item_code": {"columns": 2, "in_list_view": 1},
		"item_name": {"columns": 2, "in_list_view": 1},
		"warehouse": {"columns": 2, "in_list_view": 1},
		"package_qty": {"columns": 1, "in_list_view": 1},
		"package_uom": {"columns": 1, "in_list_view": 1},
		"qty": {"columns": 1, "in_list_view": 1},
		"stock_uom": {"columns": 1, "in_list_view": 1},
		"package_conversion_factor": {"columns": 0, "in_list_view": 0},
	}

	for fieldname, properties in field_properties.items():
		for property_name, value in properties.items():
			frappe.make_property_setter(
				{
					"doctype": "Stock Reconciliation Item",
					"doctype_or_field": "DocField",
					"fieldname": fieldname,
					"property": property_name,
					"value": value,
					"property_type": "Int",
				}
			)


def set_package_barcode_settings_defaults():
	if not frappe.db.get_single_value("Barcode Settings", "package_barcode_naming_series"):
		frappe.db.set_single_value(
			"Barcode Settings", "package_barcode_naming_series", DEFAULT_BARCODE_NAMING_SERIES
		)
	if not frappe.db.get_single_value("Barcode Settings", "package_barcode_default_qty_entry_rule"):
		frappe.db.set_single_value(
			"Barcode Settings", "package_barcode_default_qty_entry_rule", QTY_RULE_ALLOW_MANUAL
		)
