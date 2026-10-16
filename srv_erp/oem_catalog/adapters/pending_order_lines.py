import json
from uuid import UUID

import frappe
from frappe import _
from frappe.utils import getdate

from srv_erp.oem_catalog.domain.packaging import exact_positive
from srv_erp.oem_catalog.infrastructure.commands import audit, encoded, lock, save
from srv_erp.oem_catalog.permissions import authorize_context, settings

FINAL = {'Applied', 'Withdrawn'}
TOTAL_FIELDS = ('total_qty', 'total', 'base_total', 'net_total', 'base_net_total', 'total_taxes_and_charges',
                'base_total_taxes_and_charges', 'grand_total', 'base_grand_total', 'rounded_total',
                'base_rounded_total', 'rounding_adjustment', 'base_rounding_adjustment', 'discount_amount',
                'base_discount_amount', 'in_words', 'base_in_words')
TAX_FIELDS = ('tax_amount', 'base_tax_amount', 'tax_amount_after_discount_amount', 'base_tax_amount_after_discount_amount', 'total', 'base_total')


def validate_pending(doc):
    rows = doc.get('oem_pending_lines') or []
    old = doc.get_doc_before_save()
    if old:
        current_intents = {r.row_intent_id for r in rows}
        if any(r.status not in FINAL and r.row_intent_id not in current_intents for r in old.get('oem_pending_lines', [])):
            frappe.throw(_('Withdraw unresolved OEM lines with a reason before removing them.'))
    if not rows:
        doc.oem_unresolved_line_count, doc.oem_estimated_pending_amount, doc.oem_configuration_status = 0, 0, 'No OEM Lines'
        return False
    prior = {r.row_intent_id: r for r in old.get('oem_pending_lines', [])} if old else {}
    if doc.docstatus != 0 and any(row.status not in FINAL for row in rows):
        frappe.throw(_('Resolve or explicitly withdraw every OEM line before submission.'))
    if not doc.get('oem_order_entry_enabled'):
        frappe.throw(_('OEM pending lines require authorized order entry.'))
    intents, estimate, unresolved = set(), 0, 0
    context = {'customer': doc.customer, 'company': doc.company, 'brand': doc.get('brand_filter')}
    cfg = authorize_context(context, existing=bool(old and old.get('oem_pending_lines')))
    if not prior and (cfg.mode not in {'Pilot', 'Active'} or not cfg.enable_sales_order_picker):
        frappe.throw(_('OEM Sales Order entry is disabled.'))
    for row in rows:
        try: UUID(row.row_intent_id)
        except (TypeError, ValueError, AttributeError): frappe.throw(_('Invalid OEM row intent.'))
        if row.row_intent_id in intents:
            frappe.throw(_('Duplicate OEM row intent.'))
        intents.add(row.row_intent_id)
        if cfg.mode in {'Off', 'Read Only'} and row.row_intent_id not in prior:
            frappe.throw(_('New pending lines are disabled.'))
        source = frappe.get_doc('OEM Request Source', row.request_source)
        source_context = json.loads(source.context_json)
        if source.source_adapter != 'sales_order' or source.row_intent_id != row.row_intent_id or source.request != row.configuration_request:
            frappe.throw(_('Invalid OEM source association.'))
        if source.actor != frappe.session.user and source.source_document != doc.name:
            frappe.throw(_('This OEM source belongs to another user.'), frappe.PermissionError)
        if source.source_document and source.source_document != doc.name:
            frappe.throw(_('This source belongs to another order.'), frappe.PermissionError)
        if any(source_context.get(key) != context.get(key) for key in ('customer', 'company', 'brand')):
            frappe.throw(_('OEM source context changed; reconfigure this line.'))
        authorize_context(source_context, row.product, existing=row.row_intent_id in prior)
        request = frappe.get_doc('OEM Configuration Request', row.configuration_request)
        spec = frappe.get_doc('OEM Specification', row.specification)
        if request.specification != spec.name or spec.product != row.product or spec.product_revision != row.product_revision:
            frappe.throw(_('OEM specification links are inconsistent.'))
        snapshot = json.loads(row.configuration_snapshot_json or '{}')
        if snapshot.get('identity') != spec.canonical_json:
            frappe.throw(_('OEM physical snapshot cannot change.'))
        revision = frappe.get_doc('OEM Product Revision', row.product_revision)
        package = next((p for p in revision.packaging_choices if p.code == row.proposed_package_code and p.enabled), None)
        if not package or package.transaction_uom != row.proposed_uom:
            frappe.throw(_('Choose the approved pending package/UOM.'))
        quantity = exact_positive(row.proposed_qty)
        if frappe.db.get_value('UOM', row.proposed_uom, 'must_be_whole_number') and quantity != quantity.to_integral_value():
            frappe.throw(_('Pending UOM requires a whole quantity.'))
        if not row.delivery_date or getdate(row.delivery_date) < getdate(doc.transaction_date):
            frappe.throw(_('A valid pending delivery date is required.'))
        if row.warehouse and frappe.db.get_value('Warehouse', row.warehouse, 'company') != doc.company:
            frappe.throw(_('Pending warehouse belongs to another company.'))
        if row.status == 'Withdrawn':
            if not row.withdrawal_reason or not row.withdrawal_reason.strip():
                frappe.throw(_('A withdrawal reason is required.'))
        elif row.status == 'Applied':
            matches = [r for r in doc.items if r.get('oem_row_intent_id') == row.row_intent_id and r.get('oem_request_source') == row.request_source]
            actual = matches[0] if len(matches) == 1 else None
            binding = frappe.db.get_value('OEM Item Binding', {'specification': spec.name}, ['stock_item', 'binding_state'], as_dict=True)
            if request.status != 'Approved' or not actual or not binding or binding.binding_state != 'Active' or actual.item_code != binding.stock_item:
                frappe.throw(_('Applied OEM line requires its approved real order row.'))
            row.applied_sales_order_row = actual.name
        else:
            row.status = {'Pending': 'Pending', 'Approved': 'Ready', 'Rejected': 'Rejected', 'Cancelled': 'Cancelled'}[request.status]
        row.price_is_estimate = 1
        row.estimated_amount = float(quantity) * float(row.estimated_unit_rate or 0)
        if row.status not in FINAL:
            unresolved += 1; estimate += row.estimated_amount
        if row.row_intent_id in prior:
            previous = prior[row.row_intent_id]
            if any(previous.get(k) != row.get(k) for k in ('specification', 'product_revision', 'request_source', 'configuration_request', 'configuration_snapshot_json')):
                frappe.throw(_('Reconfiguration requires an explicit new source line.'))
    doc.oem_unresolved_line_count, doc.oem_estimated_pending_amount = unresolved, estimate
    doc.oem_configuration_status = 'Withdrawn' if rows and all(r.status == 'Withdrawn' for r in rows) else 'Resolved' if not unresolved else 'Needs Correction' if any(r.status in {'Rejected', 'Cancelled', 'Stale'} for r in rows) else 'Ready to Apply' if any(r.status == 'Ready' for r in rows) else 'Pending Item Approval'
    return any(row.status not in FINAL for row in rows) or bool(old and old.get('oem_pending_lines') and rows and all(row.status == 'Withdrawn' for row in rows))


def clear_empty_totals(doc):
    if doc.docstatus != 0 or doc.items or not doc.get('oem_pending_lines'):
        return
    for field in TOTAL_FIELDS:
        if doc.meta.has_field(field): doc.set(field, '' if field.endswith('in_words') else 0)
    for tax in doc.get('taxes', []):
        for field in TAX_FIELDS: tax.set(field, 0)
        tax.item_wise_tax_detail = '{}'
    for payment in doc.get('payment_schedule', []):
        for field in ('payment_amount', 'base_payment_amount', 'outstanding', 'paid_amount', 'discounted_amount'):
            if payment.meta.has_field(field): payment.set(field, 0)


def persist_sources(doc, method=None):
    if not doc.get('oem_pending_lines'): return
    old = doc.get_doc_before_save()
    present = {row.request_source for row in doc.oem_pending_lines}
    for row in doc.oem_pending_lines:
        source = lock('OEM Request Source', row.request_source)
        source.source_document, source.child_row_name = doc.name, row.name
        if row.status == 'Applied': source.result_state = 'Applied'
        elif row.status == 'Withdrawn': source.result_state = 'Abandoned'
        save(source)
    if old:
        for row in old.get('oem_pending_lines', []):
            if row.request_source not in present:
                source = lock('OEM Request Source', row.request_source)
                source.result_state = 'Abandoned'; save(source)
                audit('abandon_source', source, row.row_intent_id)
