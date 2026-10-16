import frappe
from frappe import _

from srv_erp.oem_catalog.domain.fingerprints import fingerprint
from srv_erp.oem_catalog.infrastructure.commands import Receipt, audit, lock, save
from srv_erp.oem_catalog.permissions import readable, require_role


def quarantine(binding_name, reason, idempotency_key):
    require_role('manager')
    if not reason.strip(): frappe.throw(_('A quarantine reason is required.'))
    binding = frappe.get_doc('OEM Item Binding', binding_name)
    readable('Item', binding.stock_item)
    readable('OEM Product', frappe.db.get_value('OEM Specification', binding.specification, 'product'))
    receipt = Receipt('quarantine', idempotency_key, {'binding': binding_name, 'reason': reason})
    if receipt.replay: return receipt.replay
    lock('OEM Specification', binding.specification)
    binding = lock('OEM Item Binding', binding_name)
    binding.binding_state = 'Quarantined'; save(binding)
    audit('quarantine', binding, receipt.key, {'reason': reason[:500]})
    return receipt.finish({'binding': binding.name, 'state': binding.binding_state})
