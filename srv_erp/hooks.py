app_name = "srv_erp"
app_title = "Srv Erp"
app_publisher = "Nishant Bhickta"
app_description = "Custom frappe application for SRV Electricals."
app_email = "nishantbhickta@gmail.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "srv_erp",
# 		"logo": "/assets/srv_erp/logo.png",
# 		"title": "Srv Erp",
# 		"route": "/srv_erp",
# 		"has_permission": "srv_erp.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
app_include_css = "/assets/srv_erp/css/srv_erp.css"
app_include_js = "/assets/srv_erp/js/sales_person_defaults.js"

# include js, css files in header of web template
# web_include_css = "/assets/srv_erp/css/srv_erp.css"
# web_include_js = "/assets/srv_erp/js/srv_erp.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "srv_erp/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
page_js = {
	"package-barcode-generator": "srv_erp/page/package_barcode_generator/package_barcode_generator.js",
	"zero-stock-reconciliation": "srv_erp/page/zero_stock_reconciliation/zero_stock_reconciliation.js",
}

# include js in doctype views
doctype_js = {
	"Item": [
		"public/js/item.js",
		"public/js/item/variant_select_all_dialog.js",
		"public/js/item_uom_conversion.js",
	],
	"Item Attribute": "public/js/item_attribute_variant_sync.js",
	"Brand": "public/js/item_attribute_variant_sync.js",
	"Item Price": "public/js/item_price.js",
	"Sales Order": "public/js/sales_order.js",
	"Stock Entry": [
		"public/js/package_barcode/namespace.js",
		"public/js/package_barcode/stock_table_display.js",
		"public/js/package_barcode/scan_review.js",
		"public/js/package_barcode/quantity_control.js",
		"public/js/package_barcode/stock_scanner.js",
		"public/js/package_barcode_stock.js",
	],
	"Delivery Note": [
		"public/js/package_barcode/namespace.js",
		"public/js/package_barcode/stock_table_display.js",
		"public/js/package_barcode/scan_review.js",
		"public/js/package_barcode/quantity_control.js",
		"public/js/package_barcode/stock_scanner.js",
		"public/js/package_barcode_stock.js",
	],
	"Stock Reconciliation": [
		"public/js/package_barcode/namespace.js",
		"public/js/package_barcode/stock_table_display.js",
		"public/js/package_barcode/scan_review.js",
		"public/js/package_barcode/quantity_control.js",
		"public/js/package_barcode/stock_scanner.js",
		"public/js/package_barcode_stock.js",
	],
}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
doctype_list_js = {
	"Package Barcode": "public/js/package_barcode_list.js",
	"Package Barcode Batch": "public/js/package_barcode_batch_list.js",
	"Brand": "public/js/item_attribute_variant_sync.js",
}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "srv_erp/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "srv_erp.utils.jinja_methods",
# 	"filters": "srv_erp.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "srv_erp.install.before_install"
after_install = "srv_erp.install.after_install"
before_migrate = "srv_erp.install.before_migrate"
after_migrate = ["srv_erp.install.after_migrate"]

# Uninstallation
# ------------

# before_uninstall = "srv_erp.uninstall.before_uninstall"
# after_uninstall = "srv_erp.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "srv_erp.utils.before_app_install"
# after_app_install = "srv_erp.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "srv_erp.utils.before_app_uninstall"
# after_app_uninstall = "srv_erp.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "srv_erp.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "srv_erp.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"*": {
		"before_validate": "srv_erp.selling.sales_person_user_mapping.set_mapped_sales_person",
	},
	"Item": {
		"validate": "srv_erp.item.variant_field_sync.validate_item_group_sync",
		"on_update": [
			"srv_erp.item.variant_field_sync.sync_template_item_group_to_variants",
			"srv_erp.item.variant_price_sync.sync_prices_to_new_variant",
		],
	},
	"Item Price": {
		"before_validate": "srv_erp.item.variant_price_sync.protect_managed_variant_price",
		"on_update": "srv_erp.item.variant_price_sync.sync_template_price_to_variants",
		"on_trash": "srv_erp.item.variant_price_sync.delete_managed_variant_prices",
	},
	"Item Attribute": {
		"validate": "srv_erp.item.variant_auto_creation.validate_item_attribute_brand_source",
		"on_update": "srv_erp.item.variant_auto_creation.handle_item_attribute_update",
	},
	"Brand": {
		"validate": "srv_erp.item.variant_auto_creation.validate_brand_abbreviation",
		"on_update": "srv_erp.item.variant_auto_creation.handle_brand_update",
		"on_trash": "srv_erp.item.variant_auto_creation.handle_brand_delete",
	},
	"Sales Order": {
		"validate": "srv_erp.selling.sales_order_discount.validate_sales_order_discounts",
	},
	"Sales Person": {
		"validate": "srv_erp.selling.sales_person_user_mapping.validate_sales_person_user_mapping",
		"on_update": "srv_erp.selling.sales_person_user_mapping.sync_sales_person_user_permission",
		"on_trash": "srv_erp.selling.sales_person_user_mapping.delete_sales_person_user_permission",
	},
	"Stock Entry": {
		"validate": "srv_erp.package_barcode.service.validate_stock_transaction",
	},
	"Delivery Note": {
		"validate": "srv_erp.package_barcode.service.validate_stock_transaction",
	},
	"Stock Reconciliation": {
		"before_validate": "srv_erp.package_barcode.service.sync_stock_transaction_package_quantities",
		"validate": "srv_erp.package_barcode.service.validate_stock_transaction",
	},
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"srv_erp.tasks.all"
# 	],
# 	"daily": [
# 		"srv_erp.tasks.daily"
# 	],
# 	"hourly": [
# 		"srv_erp.tasks.hourly"
# 	],
# 	"weekly": [
# 		"srv_erp.tasks.weekly"
# 	],
# 	"monthly": [
# 		"srv_erp.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "srv_erp.install.before_tests"

# Override DocType Class
# ------------------------------
# Frappe v15 does not apply extend_doctype_class, so Item Price uses a small
# subclass that only relaxes ERPNext's template-item restriction.
override_doctype_class = {
	"Item Price": "srv_erp.item.variant_price_sync.TemplateItemPrice",
}

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "srv_erp.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "srv_erp.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["srv_erp.utils.before_request"]
# after_request = ["srv_erp.utils.after_request"]

# Job Events
# ----------
# before_job = ["srv_erp.utils.before_job"]
# after_job = ["srv_erp.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"srv_erp.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []
