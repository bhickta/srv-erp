import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def setup():
    if not frappe.db.exists('DocType', 'OEM Catalog Settings'):
        return
    for role in ('OEM Catalog User', 'OEM Catalog Approver', 'OEM Catalog Manager'):
        if not frappe.db.exists('Role', role):
            frappe.get_doc({'doctype': 'Role', 'role_name': role, 'desk_access': 1}).insert(ignore_permissions=True)
    from .indexes import execute
    execute()
    fields = {
        'Sales Order': [
            {'fieldname': 'oem_line_cards', 'label': 'OEM Order Lines', 'fieldtype': 'HTML', 'insert_after': 'items', 'hidden': 1},
            {'fieldname': 'oem_pending_lines', 'label': 'OEM Pending Lines', 'fieldtype': 'Table', 'options': 'OEM Pending Sales Order Line', 'insert_after': 'items', 'hidden': 1},
            {'fieldname': 'oem_order_entry_enabled', 'label': 'OEM Order Entry', 'fieldtype': 'Check', 'default': '0', 'hidden': 1},
            {'fieldname': 'oem_configuration_status', 'label': 'OEM Configuration Status', 'fieldtype': 'Data', 'read_only': 1},
            {'fieldname': 'oem_unresolved_line_count', 'label': 'Unresolved OEM Lines', 'fieldtype': 'Int', 'read_only': 1},
            {'fieldname': 'oem_estimated_pending_amount', 'label': 'Estimated Pending Amount', 'fieldtype': 'Currency', 'read_only': 1},
        ],
        'Sales Order Item': [
            {'fieldname': 'oem_specification', 'label': 'OEM Specification', 'fieldtype': 'Link', 'options': 'OEM Specification'},
            {'fieldname': 'oem_request_source', 'label': 'OEM Request Source', 'fieldtype': 'Link', 'options': 'OEM Request Source'},
            {'fieldname': 'oem_row_intent_id', 'label': 'OEM Row Intent', 'fieldtype': 'Data'},
            {'fieldname': 'oem_snapshot_json', 'label': 'OEM Snapshot', 'fieldtype': 'Long Text'},
            {'fieldname': 'oem_snapshot_hash', 'label': 'OEM Snapshot Hash', 'fieldtype': 'Data'},
        ],
        'Package Barcode Batch': [
            {'fieldname': 'oem_specification', 'label': 'OEM Specification', 'fieldtype': 'Link', 'options': 'OEM Specification'},
            {'fieldname': 'oem_barcode_intent', 'label': 'OEM Barcode Intent', 'fieldtype': 'Link', 'options': 'OEM Barcode Intent'},
            {'fieldname': 'oem_package_snapshot_json', 'label': 'OEM Package Snapshot', 'fieldtype': 'Long Text'},
            {'fieldname': 'oem_package_snapshot_hash', 'label': 'OEM Package Snapshot Hash', 'fieldtype': 'Data'},
        ],
    }
    for doctype in ('Sales Order Item', 'Package Barcode Batch'):
        for field in fields[doctype]:
            field.update(hidden=1, read_only=1)
    create_custom_fields(fields, update=True)
