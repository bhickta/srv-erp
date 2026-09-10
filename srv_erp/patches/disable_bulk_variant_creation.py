import frappe

from srv_erp.masters.dynamic_item.configuration import clear_settings_cache
from srv_erp.masters.setup import setup_masters_module


def execute():
	setup_masters_module()
	frappe.db.set_single_value("Masters Settings", "allow_bulk_variant_creation", 0)
	frappe.db.set_single_value("Masters Settings", "enable_dynamic_item_requests", 0)
	frappe.db.set_single_value("Masters Settings", "enforce_variant_approval", 1)
	frappe.db.set_single_value("SRV Settings", "auto_create_variants_on_brand_update", 0)
	clear_settings_cache()
