import json

import frappe
from frappe import _
from frappe.utils import now_datetime

from srv_erp.oem_catalog.domain.fingerprints import fingerprint
from srv_erp.oem_catalog.infrastructure.commands import Receipt, audit, digest, encoded, get_or_insert, insert, lock, save
from srv_erp.oem_catalog.infrastructure.dto import object_input
from srv_erp.oem_catalog.permissions import authorize_context, readable, require_role
from .configure import validated


def source_signature(item):
    return digest(item.as_dict())


def verify_legacy(item, identity, revision, package, evidence):
    if item.disabled or item.has_variants or not item.is_stock_item or item.stock_uom != revision.stock_uom:
        frappe.throw(_('LEGACY_MAPPING_REQUIRED: source is ineligible.'))
    brands = {row.attribute_value for row in item.attributes if row.attribute == 'Brand'}
    if item.brand: brands.add(item.brand)
    if len(brands) > 1 or (brands and next(iter(brands)) != identity.values['brand']):
        frappe.throw(_('CONFIGURATION_CONFLICT: physical Brand disagrees.'))
    for key in identity.values:
        if not isinstance(evidence.get(key), str) or not evidence[key].strip():
            frappe.throw(_('LEGACY_MAPPING_REQUIRED: every physical fact requires reviewed evidence.'))
    factors = {row.uom: str(row.conversion_factor) for row in item.uoms}
    from decimal import Decimal
    if package.uom not in factors or Decimal(factors[package.uom]) != package.factor:
        frappe.throw(_('CONFIGURATION_CONFLICT: adoption cannot add or change UOM factors.'))


def preview_import(scope, kind, idempotency_key):
    require_role('manager')
    scope = object_input(scope, {'payload', 'stock_items', 'evidence'})
    payload, product, revision, identity, provenance, package = validated(scope['payload'])
    authorize_context(payload['context'], product.name, write=True, capability='manager')
    sources = scope.get('stock_items', [])
    if not isinstance(sources, list) or not 1 <= len(sources) <= 100 or len(sources) != len(set(sources)):
        frappe.throw(_('Choose 1 to 100 distinct source Items.'))
    if kind not in {'Product Bootstrap', 'Legacy Mapping'}:
        frappe.throw(_('Unsupported review kind.'))
    receipt = Receipt('preview_import', idempotency_key, {'scope': scope, 'kind': kind})
    if receipt.replay: return receipt.replay
    rows = []
    for name in sources:
        item = readable('Item', name)
        reason, status = '', 'Candidate'
        if kind == 'Legacy Mapping':
            try: verify_legacy(item, identity, revision, package, scope.get('evidence', {}))
            except frappe.ValidationError:
                reason, status = _('Source needs complete physical/UOM review.'), 'Conflict'
        proposed = {'payload': payload, 'canonical_json': identity.canonical_json, 'identity_hash': identity.digest,
                    'evidence': scope.get('evidence', {}), 'source_name': item.name,
                    'suggested_product': {'display_name': item.item_name, 'item_group': item.item_group, 'stock_uom': item.stock_uom}}
        rows.append({'source_record': item.name, 'target_product': product.name, 'source_fingerprint': source_signature(item),
                     'proposed_json': encoded(proposed), 'status': status, 'reason': reason})
    review = insert('OEM Import Review', kind=kind, source_scope_json=encoded({'product': product.name}), plan_hash=digest(rows),
                    status='Previewed', summary_json=encoded({'candidates': len(rows), 'duplicates_require_single_selection': kind == 'Legacy Mapping' and len(rows) > 1}), rows=rows)
    audit('preview_import', review, receipt.key)
    return receipt.finish({'review': review.name, 'plan_hash': review.plan_hash, 'rows': rows})


def approve_import(review_name, plan_hash, selected_rows, idempotency_key):
    require_role('manager')
    review = frappe.get_doc('OEM Import Review', review_name)
    selected_rows = json.loads(selected_rows) if isinstance(selected_rows, str) else selected_rows
    if not isinstance(selected_rows, list) or len(selected_rows) != 1:
        frappe.throw(_('Select one canonical Item per physical specification.'))
    receipt = Receipt('approve_import', idempotency_key, {'review': review_name, 'hash': plan_hash, 'rows': selected_rows})
    if receipt.replay: return receipt.replay
    review = lock('OEM Import Review', review_name)
    if review.status != 'Previewed' or review.plan_hash != plan_hash or review.kind != 'Legacy Mapping':
        frappe.throw(_('STALE_CONFIGURATION: review is not eligible for adoption.'))
    for row in review.rows:
        proposal = json.loads(row.proposed_json)
        authorize_context(proposal['payload']['context'], row.target_product, write=True, capability='manager')
        if row.name in selected_rows:
            if row.status != 'Candidate': frappe.throw(_('Conflicted sources cannot be approved.'))
            row.status = 'Approved'
        else: row.status = 'Skipped'
    if not any(r.status == 'Approved' for r in review.rows): frappe.throw(_('Choose a row from this review.'))
    review.status, review.reviewed_by, review.reviewed_on = 'Approved', frappe.session.user, now_datetime()
    save(review); audit('approve_import', review, receipt.key)
    return receipt.finish({'review': review.name, 'status': review.status})


def apply_import(review_name, plan_hash, idempotency_key):
    require_role('manager')
    receipt = Receipt('apply_import', idempotency_key, {'review': review_name, 'hash': plan_hash})
    if receipt.replay: return receipt.replay
    review = lock('OEM Import Review', review_name)
    if review.status != 'Approved' or review.plan_hash != plan_hash or review.kind != 'Legacy Mapping':
        frappe.throw(_('STALE_CONFIGURATION: review is not approved.'))
    results = []
    for row in review.rows:
        if row.status != 'Approved': continue
        proposed = json.loads(row.proposed_json)
        payload, product, revision, identity, provenance, package = validated(proposed['payload'])
        authorize_context(payload['context'], product.name, write=True, capability='manager')
        item = readable('Item', row.source_record)
        if source_signature(item) != row.source_fingerprint:
            frappe.throw(_('ITEM_DRIFT: source changed since preview.'))
        verify_legacy(item, identity, revision, package, proposed['evidence'])
        spec, _ = get_or_insert('OEM Specification', {'identity_hash': identity.digest},
                               {'identity_hash': identity.digest, 'canonical_json': identity.canonical_json, 'product': product.name,
                                'product_revision': revision.name, 'identity_namespace': revision.identity_namespace,
                                'summary': product.display_name, 'release_state': 'Unreleased'})
        spec = lock('OEM Specification', spec.name)
        if spec.canonical_json != identity.canonical_json: frappe.throw(_('Identity collision.'))
        if frappe.db.exists('OEM Item Binding', {'specification': spec.name}) or frappe.db.exists('OEM Item Binding', {'stock_item': item.name}):
            frappe.throw(_('CONFIGURATION_CONFLICT: specification or source already bound.'))
        binding = insert('OEM Item Binding', specification=spec.name, stock_item=item.name, ownership='Legacy Adopted',
                         binding_state='Active', expected_stock_fingerprint=fingerprint(item.as_dict()),
                         bound_by=frappe.session.user, bound_on=now_datetime(), legacy_evidence_json=encoded(proposed['evidence']))
        spec.release_state = 'Released'; save(spec)
        row.target_specification, row.status = spec.name, 'Applied'
        audit('adopt_item', binding, receipt.key)
        results.append({'binding': binding.name, 'stock_item': item.name})
    review.status = 'Applied'; save(review)
    audit('apply_import', review, receipt.key)
    return receipt.finish({'review': review.name, 'bindings': results})
