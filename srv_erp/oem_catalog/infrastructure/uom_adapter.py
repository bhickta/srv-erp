from contextvars import ContextVar
from decimal import Decimal

import frappe
from frappe import _

from srv_erp.oem_catalog.domain.fingerprints import fingerprint
from srv_erp.oem_catalog.domain.packaging import exact_positive
from .commands import lock, save

EXTENDING_UOM = ContextVar('oem_approved_uom_extension', default=False)


def append_approved(binding, proposals):
    item = lock('Item', binding.stock_item)
    for proposal in proposals:
        uom, factor = proposal['uom'], exact_positive(proposal['factor'])
        frappe.get_doc('UOM', uom).check_permission('read')
        existing = next((row for row in item.uoms if row.uom == uom), None)
        if existing:
            if Decimal(str(existing.conversion_factor)) != factor:
                frappe.throw(_('CONFIGURATION_CONFLICT: existing UOM factor cannot change.'))
        else: item.append('uoms', {'uom': uom, 'conversion_factor': str(factor)})
    token = EXTENDING_UOM.set(True)
    try:
        item.save(ignore_permissions=True)
        binding.expected_stock_fingerprint = fingerprint(item.as_dict())
        save(binding)
    finally: EXTENDING_UOM.reset(token)
    return item


def valid_append(old, new):
    old_payload, new_payload = old.as_dict(), new.as_dict()
    old_uoms = {r.uom: Decimal(str(r.conversion_factor)) for r in old.uoms}
    new_uoms = {r.uom: Decimal(str(r.conversion_factor)) for r in new.uoms}
    if any(new_uoms.get(key) != value for key, value in old_uoms.items()): return False
    new_payload['uoms'] = old_payload['uoms']
    return fingerprint(old_payload) == fingerprint(new_payload)
