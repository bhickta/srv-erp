import frappe

from srv_erp.masters.dynamic_item.configuration import clear_settings_cache


def execute():
	frappe.db.set_single_value("Masters Settings", "allow_dynamic_attributes", 0)
	frappe.db.sql(
		"""
		update `tabDynamic Variant Profile Attribute`
		set allow_new_values = 0
		where ifnull(allow_new_values, 0) != 0
		"""
	)
	clear_settings_cache()
