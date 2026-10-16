import frappe
from frappe import _

from srv_erp.oem_catalog.domain.fingerprints import fingerprint
from srv_erp.oem_catalog.permissions import available


def protect(doc, method=None):
    if doc.is_new() or not available(): return
    from srv_erp.oem_catalog.infrastructure.uom_adapter import EXTENDING_UOM, valid_append
    if EXTENDING_UOM.get() and valid_append(doc.get_doc_before_save(), doc): return
    binding = frappe.db.get_value('OEM Item Binding', {'stock_item': doc.name}, ['ownership', 'expected_stock_fingerprint'], as_dict=True)
    if binding and binding.ownership == 'Module Created' and fingerprint(doc.as_dict()) != binding.expected_stock_fingerprint:
        frappe.throw(_('Released OEM physical fields and UOM factors are immutable.'))


def protect_delete(doc, method=None):
    if available() and frappe.db.exists('OEM Item Binding', {'stock_item': doc.name}):
        frappe.throw(_('A bound OEM Item must be retained for audit.'))
