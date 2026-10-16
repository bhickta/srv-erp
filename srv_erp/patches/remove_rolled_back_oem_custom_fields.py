"""Detach OEM fields left behind by the rollback of PR #94.

Deleting Custom Field documents removes form metadata, not database columns or
OEM records. Keep that data available for a later, deliberate OEM rollout.
"""

import frappe


OEM_CUSTOM_FIELDS = {
	"Sales Order": (
		"oem_line_cards",
		"oem_pending_lines",
		"oem_order_entry_enabled",
		"oem_configuration_status",
		"oem_unresolved_line_count",
		"oem_estimated_pending_amount",
	),
	"Sales Order Item": (
		"oem_specification",
		"oem_request_source",
		"oem_row_intent_id",
		"oem_snapshot_json",
		"oem_snapshot_hash",
	),
	"Package Barcode Batch": (
		"oem_specification",
		"oem_barcode_intent",
		"oem_package_snapshot_json",
		"oem_package_snapshot_hash",
	),
}


def execute():
	# Do not detach fields if OEM has intentionally been restored before migration.
	if "OEM Catalog" in frappe.get_module_list("srv_erp"):
		return

	for doctype, fieldnames in OEM_CUSTOM_FIELDS.items():
		for name in frappe.get_all(
			"Custom Field",
			filters={"dt": doctype, "fieldname": ("in", fieldnames)},
			pluck="name",
		):
			frappe.delete_doc("Custom Field", name, ignore_permissions=True)
		frappe.clear_cache(doctype=doctype)
