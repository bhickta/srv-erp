import json

import frappe
from frappe import _

from srv_erp.oem_catalog.infrastructure.commands import Receipt
from srv_erp.oem_catalog.infrastructure.dto import object_input
from srv_erp.oem_catalog.permissions import authorize_context
from .configure import active_binding

ORDER_FIELDS = {'name', 'customer', 'company', 'transaction_date', 'delivery_date', 'brand_filter', 'currency', 'selling_price_list',
                'oem_order_entry_enabled', 'oem_pending_lines', 'items', 'taxes_and_charges', 'set_warehouse', 'po_no', 'po_date'}
PENDING_FIELDS = {'name', 'row_intent_id', 'product', 'product_revision', 'specification', 'configuration_request', 'request_source',
                  'configuration_snapshot_json', 'physical_summary', 'proposed_qty', 'proposed_uom', 'proposed_package_code', 'delivery_date',
                  'warehouse', 'estimated_unit_rate', 'commercial_notes', 'status', 'applied_sales_order_row', 'withdrawal_reason'}


def validate_apply(source_name, document_context, row_intent_id):
    context = object_input(document_context, {'document', 'modified', 'customer', 'company', 'brand'})
    source = frappe.get_doc('OEM Request Source', source_name)
    if source.row_intent_id != row_intent_id or source.source_adapter != 'sales_order':
        frappe.throw(_('Invalid source intent.'))
    if source.actor != frappe.session.user and source.source_document != context.get('document'):
        frappe.throw(_('Source is unavailable.'), frappe.PermissionError)
    if source.source_document and source.source_document != context.get('document'):
        frappe.throw(_('Source belongs to another order.'), frappe.PermissionError)
    if context.get('document'):
        doc = frappe.get_doc('Sales Order', context['document']); doc.check_permission('write')
        if doc.docstatus != 0 or str(doc.modified) != context.get('modified'):
            frappe.throw(_('STALE_CONFIGURATION: refresh the draft order.'))
    elif not frappe.has_permission('Sales Order', 'create'):
        frappe.throw(_('Sales Order creation is unavailable.'), frappe.PermissionError)
    actual_context = {k: context.get(k) for k in ('customer', 'company', 'brand')}
    original = json.loads(source.context_json)
    if any(original.get(k) != actual_context.get(k) for k in actual_context):
        frappe.throw(_('STALE_CONFIGURATION: source context changed.'))
    request = frappe.get_doc('OEM Configuration Request', source.request)
    spec = frappe.get_doc('OEM Specification', request.specification)
    authorize_context(original, spec.product, existing=True)
    if request.status != 'Approved' or source.result_state not in {'Ready', 'Applied'}:
        frappe.throw(_('Request is not ready to apply.'))
    binding, item = active_binding(spec.name, original)
    return {'item_code': item.name, 'oem_specification': spec.name, 'oem_request_source': source.name,
            'oem_row_intent_id': row_intent_id, 'oem_snapshot_json': spec.canonical_json}


def save_order(order_payload, expected_modified, idempotency_key):
    payload = object_input(order_payload, ORDER_FIELDS)
    name = payload.pop('name', None)
    if name:
        doc = frappe.get_doc('Sales Order', name); doc.check_permission('write')
        if doc.docstatus != 0: frappe.throw(_('Only draft orders are editable.'))
    else:
        if not frappe.has_permission('Sales Order', 'create'): frappe.throw(_('Sales Order creation is unavailable.'), frappe.PermissionError)
        doc = frappe.new_doc('Sales Order')
    receipt = Receipt('save_pending_order', idempotency_key, {'order': dict(payload, name=name), 'modified': expected_modified})
    if receipt.replay:
        frappe.get_doc('Sales Order', receipt.replay['name']).check_permission('read')
        return receipt.replay
    if name and str(doc.modified) != expected_modified:
        frappe.throw(_('STALE_CONFIGURATION: refresh the saved Sales Order.'))
    for line in payload.get('oem_pending_lines', []): object_input(line, PENDING_FIELDS)
    # The normal form route supports complete real rows. This focused command
    # currently accepts pending lines and preserves existing real rows server-side.
    if 'items' in payload:
        frappe.throw(_('Use normal item-detail form handlers to save resolved rows.'))
    doc.update(payload)
    doc.save()
    return receipt.finish({'name': doc.name, 'modified': str(doc.modified), 'docstatus': int(doc.docstatus), 'configuration_status': doc.oem_configuration_status})
