import frappe
from frappe import _

from srv_erp.oem_catalog.permissions import available, authorize_context


def guard_legacy_generation(item_code):
    if not available(): return
    if frappe.db.exists('OEM Item Binding', {'stock_item': item_code}):
        frappe.throw(_('Use the governed OEM barcode command for this managed Item.'), frappe.PermissionError)


def authorize_batch(batch_name):
    if not available(): return
    intent_name = frappe.db.get_value('OEM Barcode Intent', {'barcode_batch': batch_name}, 'name')
    if not intent_name: return
    intent = frappe.get_doc('OEM Barcode Intent', intent_name)
    context = {key: intent.get(key) for key in ('customer', 'company') if intent.get(key)}
    spec = frappe.get_doc('OEM Specification', intent.specification)
    import json
    context['brand'] = json.loads(spec.canonical_json)['attributes']['brand']
    authorize_context(context, spec.product, existing=True)
    frappe.get_doc('Package Barcode Batch', batch_name).check_permission('read')
    frappe.get_doc('Item', frappe.get_doc('OEM Item Binding', intent.binding).stock_item).check_permission('read')


def authorize_selection(names=None, batches=None):
    if not available(): return
    if names:
        batches = frappe.get_all('Package Barcode', filters={'name': ['in', names]}, pluck='generation_batch')
    for batch in set(batches or []): authorize_batch(batch)
