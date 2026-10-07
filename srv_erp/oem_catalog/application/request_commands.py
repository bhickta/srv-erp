import json
from uuid import uuid4

import frappe
from frappe import _
from frappe.utils import now_datetime

from srv_erp.oem_catalog.domain.transitions import decide
from srv_erp.oem_catalog.infrastructure.commands import Receipt, audit, digest, encoded, get_or_insert, insert, lock, notify, save
from srv_erp.oem_catalog.infrastructure.dto import configuration_input
from srv_erp.oem_catalog.permissions import authorize_context, request_access, settings
from .configure import active_binding, validated


def submit(payload, idempotency_key):
    payload = configuration_input(payload)
    authorize_context(payload['context'], payload['product'], write=True)
    receipt = Receipt('submit', idempotency_key, payload)
    if receipt.replay:
        if receipt.replay.get('item_code'):
            frappe.get_doc('Item', receipt.replay['item_code']).check_permission('read')
        return receipt.replay
    payload, product, revision, identity, provenance, package = validated(payload)
    spec, _ = get_or_insert('OEM Specification', {'identity_hash': identity.digest},
                           {'identity_hash': identity.digest, 'canonical_json': identity.canonical_json,
                            'product': product.name, 'product_revision': revision.name, 'identity_namespace': revision.identity_namespace,
                            'summary': product.display_name, 'release_state': 'Unreleased',
                            'identity_values': [{'attribute_key': k, 'typed_value_json': encoded(v), 'display_label_snapshot': k} for k, v in identity.values.items()]})
    spec = lock('OEM Specification', spec.name)
    if spec.canonical_json != identity.canonical_json:
        frappe.throw(_('CONFIGURATION_CONFLICT: identity collision.'))
    binding, item = active_binding(spec.name, payload['context'])
    kind, active_key, proposals = 'Release Specification', 'release:' + identity.digest, []
    if binding:
        from decimal import Decimal
        factor = next((row.conversion_factor for row in item.uoms if row.uom == package.uom), 1 if package.uom == item.stock_uom else None)
        if factor is None:
            kind, proposals = 'Add Transaction UOM', [{'uom': package.uom, 'factor': str(package.factor)}]
            active_key = 'uom:' + binding.name + ':' + digest(proposals)
        elif Decimal(str(factor)) != package.factor:
            frappe.throw(_('CONFIGURATION_CONFLICT: released UOM factor cannot change.'))
        else:
            return receipt.finish({'api_version': 1, 'outcome': 'EXISTING', 'specification': spec.name, 'item_code': item.name, 'binding': binding.name})
    snapshot = {'revision': revision.name, 'publication_hash': revision.publication_hash, 'identity': identity.canonical_json,
                'values': identity.values, 'provenance': provenance,
                'package': {'code': package.code, 'uom': package.uom, 'factor': str(package.factor)}}
    request, created = get_or_insert('OEM Configuration Request', {'active_key': active_key},
                                    {'kind': kind, 'binding': binding.name if binding else None, 'proposed_uoms_json': encoded(proposals), 'specification': spec.name,
                                     'submitted_payload_json': encoded(payload), 'configuration_snapshot_json': encoded(snapshot),
                                     'payload_hash': digest(payload), 'active_key': active_key, 'status': 'Pending',
                                     'requested_by': frappe.session.user, 'requested_on': now_datetime(), 'expected_configuration_token': payload['configuration_token']})
    source = payload['source']
    intent = source.get('row_intent_id') or str(uuid4())
    origin, _ = get_or_insert('OEM Request Source', {'request': request.name, 'actor': frappe.session.user, 'row_intent_id': intent},
                             {'request': request.name, 'actor': frappe.session.user, 'row_intent_id': intent,
                              'source_adapter': source.get('adapter', 'standalone'), 'source_doctype': source.get('doctype'),
                              'source_document': source.get('document'), 'source_field': source.get('field'),
                              'document_modified_token': source.get('modified'), 'context_json': encoded(payload['context']), 'result_state': 'Pending'})
    audit('submit' if created else 'attach_source', request, receipt.key)
    if created: notify(request)
    return receipt.finish({'api_version': 1, 'outcome': 'PENDING', 'specification': spec.name, 'request': request.name,
                           'source': origin.name, 'row_intent_id': intent, 'snapshot': snapshot, 'item_code': None})


def terminal(request_name, expected_modified, reason, idempotency_key, target):
    request = frappe.get_doc('OEM Configuration Request', request_name)
    payload = request_access(request, approver=target == 'Rejected')
    if target == 'Cancelled' and request.requested_by != frappe.session.user:
        frappe.throw(_('Only the requester can cancel this request.'), frappe.PermissionError)
    receipt = Receipt(target.lower(), idempotency_key, {'request': request_name, 'modified': expected_modified, 'reason': reason})
    if receipt.replay: return receipt.replay
    lock('OEM Specification', request.specification)
    request = lock('OEM Configuration Request', request_name)
    if str(request.modified) != expected_modified:
        frappe.throw(_('REQUEST_STATE_CONFLICT: refresh this request.'))
    decide(request.status, target, request.requested_by, frappe.session.user, reason)
    request.status, request.active_key, request.reason = target, None, reason.strip()
    request.approved_by, request.approved_on = frappe.session.user, now_datetime()
    save(request)
    for name in frappe.get_all('OEM Request Source', filters={'request': request.name}, pluck='name'):
        source = lock('OEM Request Source', name)
        source.result_state = 'Abandoned'
        save(source)
    audit(target.lower(), request, receipt.key)
    notify(request, decision=True)
    return receipt.finish({'request': request.name, 'status': request.status})
