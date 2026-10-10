from contextlib import contextmanager
from contextvars import ContextVar

import frappe
from frappe import _
from frappe.model.document import Document

_CAPABILITY = ContextVar('oem_internal_command', default=False)
MASTERS = {'OEM Product', 'OEM Product Revision', 'OEM Option Set', 'OEM Asset', 'OEM Asset Revision',
           'OEM Customer Brand', 'OEM Default Profile', 'OEM Customer Item Alias', 'OEM Catalog Settings'}


@contextmanager
def internal_command():
    token = _CAPABILITY.set(True)
    try:
        yield
    finally:
        _CAPABILITY.reset(token)


class OEMDocument(Document):
    def validate(self):
        if self.meta.istable:
            return
        if self.doctype not in MASTERS and not _CAPABILITY.get():
            frappe.throw(_('This record can only be changed through an OEM command.'), frappe.PermissionError)
        old = self.get_doc_before_save()
        if self.doctype in MASTERS:
            from srv_erp.oem_catalog.application.publication import validate_master
            validate_master(self, old, _CAPABILITY.get())
        elif old:
            fixed = {
                'OEM Specification': ('canonical_json', 'identity_hash', 'product', 'product_revision', 'identity_namespace'),
                'OEM Item Binding': ('specification', 'stock_item', 'ownership', 'expected_stock_fingerprint'),
                'OEM Configuration Request': ('specification', 'submitted_payload_json', 'configuration_snapshot_json', 'payload_hash', 'requested_by'),
                'OEM Request Source': ('request', 'actor', 'row_intent_id', 'context_json'),
                'OEM Audit Event': tuple(self.meta.get_valid_columns()),
            }.get(self.doctype, ())
            for field in fixed:
                from .uom_adapter import EXTENDING_UOM
                if field == 'expected_stock_fingerprint' and EXTENDING_UOM.get(): continue
                if field not in ('modified', 'modified_by') and self.get(field) != old.get(field):
                    frappe.throw(_('OEM immutable content cannot be changed.'))

    def on_trash(self):
        if not self.meta.istable:
            frappe.throw(_('OEM audit and referenced catalogue records are retained. Retire them instead.'))
