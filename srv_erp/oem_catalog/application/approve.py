import json

import frappe
from frappe import _
from frappe.utils import now_datetime

from srv_erp.oem_catalog.domain.canonicalization import canonicalize
from srv_erp.oem_catalog.domain.fingerprints import fingerprint
from srv_erp.oem_catalog.domain.transitions import decide
from srv_erp.oem_catalog.infrastructure.commands import Receipt, audit, encoded, insert, lock, notify, save
from srv_erp.oem_catalog.infrastructure.item_materializer import materialize
from srv_erp.oem_catalog.permissions import authorize_context, request_access
from .configure import active_binding, validated


def approve(request_name, expected_modified, reason, idempotency_key):
    request = frappe.get_doc('OEM Configuration Request', request_name)
    payload = request_access(request, approver=True)
    cfg = authorize_context(payload['context'], payload['product'], write=True, capability='approver')
    receipt = Receipt('approve', idempotency_key, {'request': request_name, 'modified': expected_modified, 'reason': reason})
    if receipt.replay:
        if receipt.replay.get('item_code'): frappe.get_doc('Item', receipt.replay['item_code']).check_permission('read')
        return receipt.replay
    spec = lock('OEM Specification', request.specification)
    request = lock('OEM Configuration Request', request_name)
    if request.status == 'Approved':
        binding, item = active_binding(spec.name, payload['context'], current=True)
        return receipt.finish({'request': request.name, 'binding': binding.name, 'item_code': item.name, 'status': 'Approved'})
    if str(request.modified) != expected_modified:
        frappe.throw(_('REQUEST_STATE_CONFLICT: refresh this request.'))
    decide(request.status, 'Approved', request.requested_by, frappe.session.user, reason, bool(cfg.allow_self_approval))
    payload_now, product, revision, identity, provenance, package = validated(payload)
    if identity.canonical_json != spec.canonical_json:
        frappe.throw(_('STALE_CONFIGURATION: physical configuration changed.'))
    binding, item = active_binding(spec.name, payload['context'], current=True)
    if request.kind == 'Add Transaction UOM':
        if not binding or not cfg.allow_create_items: frappe.throw(_('Approved UOM writes are disabled or binding is unavailable.'))
        from srv_erp.oem_catalog.infrastructure.uom_adapter import append_approved
        binding = lock('OEM Item Binding', binding.name)
        item = append_approved(binding, json.loads(request.proposed_uoms_json))
    elif not binding:
        item = materialize(product, revision, identity, payload['context'], cfg)
        binding = insert('OEM Item Binding', specification=spec.name, stock_item=item.name, ownership='Module Created',
                         binding_state='Active', expected_stock_fingerprint=fingerprint(item.as_dict()),
                         created_from_request=request.name, bound_by=frappe.session.user, bound_on=now_datetime())
    spec.release_state = 'Released'; save(spec)
    request.status, request.active_key, request.binding = 'Approved', None, binding.name
    request.approved_by, request.approved_on, request.reason = frappe.session.user, now_datetime(), reason or ''
    request.decision_snapshot_json = encoded({'binding': binding.name, 'item': item.name, 'self_approval_exception': request.requested_by == frappe.session.user})
    save(request)
    for name in frappe.get_all('OEM Request Source', filters={'request': request.name, 'result_state': 'Pending'}, pluck='name'):
        source = lock('OEM Request Source', name)
        source.result_state = 'Ready'; save(source)
    audit('approve', request, receipt.key)
    notify(request, decision=True)
    return receipt.finish({'api_version': 1, 'request': request.name, 'binding': binding.name, 'item_code': item.name, 'status': 'Approved'})
