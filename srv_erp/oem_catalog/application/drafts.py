from uuid import UUID

import frappe
from frappe import _
from frappe.utils import now_datetime

from srv_erp.oem_catalog.domain.canonicalization import typed_value
from srv_erp.oem_catalog.infrastructure.commands import Receipt, digest, encoded, insert, save
from srv_erp.oem_catalog.infrastructure.dto import configuration_input
from srv_erp.oem_catalog.permissions import authorize_context
from .configure import load_configuration


def save_draft(payload, idempotency_key, draft=None, expected_modified=None):
    payload = configuration_input(payload)
    authorize_context(payload['context'], payload['product'], write=True)
    receipt = Receipt('save_draft', idempotency_key, {'payload': payload, 'draft': draft, 'modified': expected_modified})
    if receipt.replay: return receipt.replay
    loaded = load_configuration(payload['product'], payload['context'])
    attributes = {a.key: a for a in loaded[2].attributes}
    for key, value in payload['values'].items():
        if key not in attributes: frappe.throw(_('Unknown draft attribute.'))
        if value is not None and value != '': typed_value(attributes[key], value)
    values = {'draft_owner': frappe.session.user, 'context_json': encoded(payload['context']), 'product_revision': loaded[1].name,
              'values_json': encoded(payload['values']), 'value_provenance_json': encoded(loaded[-2]),
              'configuration_hash': digest(payload), 'last_validated_on': now_datetime()}
    if draft:
        doc = frappe.get_doc('OEM Configuration Draft', draft)
        if doc.draft_owner != frappe.session.user or str(doc.modified) != expected_modified:
            frappe.throw(_('STALE_CONFIGURATION: private draft changed.'), frappe.PermissionError)
        doc.update(values); save(doc)
    else: doc = insert('OEM Configuration Draft', **values)
    return receipt.finish({'draft': doc.name, 'modified': str(doc.modified)})
