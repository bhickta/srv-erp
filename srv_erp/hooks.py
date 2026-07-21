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
# app_include_css = "/assets/srv_erp/css/srv_erp.css"
# app_include_js = "/assets/srv_erp/js/srv_erp.js"

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
	],
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
	"Stock Entry": {
		"validate": "srv_erp.package_barcode.service.validate_stock_transaction",
	},
	"Delivery Note": {
		"validate": "srv_erp.package_barcode.service.validate_stock_transaction",
	},
	"Stock Reconciliation": {
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

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "srv_erp.custom.task.CustomTaskMixin"
# }

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
