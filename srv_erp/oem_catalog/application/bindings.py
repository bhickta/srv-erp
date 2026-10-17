"""Authoritative released Item lookup and stock-integrity checks."""
import frappe
from frappe import _

from srv_erp.oem_catalog.domain.fingerprints import fingerprint


def active_binding(specification, context, permission=True, current=False):
    name = frappe.db.get_value('OEM Item Binding', {'specification': specification}, 'name', for_update=current)
    if not name: return None, None
    binding = frappe.get_doc('OEM Item Binding', name, for_update=current)
    if binding.binding_state != 'Active':
        frappe.throw(_('ITEM_DRIFT: binding is unavailable.'))
    item = frappe.get_doc('Item', binding.stock_item, for_update=current)
    if permission: item.check_permission('read')
    if item.disabled or item.has_variants:
        frappe.throw(_('DISABLED_MATCH: exact Item is unavailable.'))
    if fingerprint(item.as_dict()) != binding.expected_stock_fingerprint:
        frappe.throw(_('ITEM_DRIFT: stock identity changed.'))
    return binding, item
