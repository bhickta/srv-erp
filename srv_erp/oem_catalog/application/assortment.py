import json

import frappe
from frappe import _
from frappe.utils import now_datetime

from srv_erp.oem_catalog.infrastructure.commands import Receipt, digest, get_or_insert, save
from srv_erp.oem_catalog.infrastructure.dto import object_input
from srv_erp.oem_catalog.permissions import authorize_context
from .configure import active_binding


def alias(payload, idempotency_key):
    payload = object_input(payload, {'customer', 'specification', 'customer_item_code', 'display_name', 'favourite'})
    if 'favourite' in payload and not isinstance(payload['favourite'], bool): frappe.throw(_('Favourite must be a boolean.'))
    spec = frappe.get_doc('OEM Specification', payload['specification'])
    brand = json.loads(spec.canonical_json)['attributes']['brand']
    context = {'customer': payload['customer'], 'brand': brand}
    authorize_context(context, spec.product, write=True)
    binding, item = active_binding(spec.name, context)
    if not binding: frappe.throw(_('Only released specifications can be added to an assortment.'))
    receipt = Receipt('set_alias', idempotency_key, payload)
    if receipt.replay: return receipt.replay
    doc, _ = get_or_insert('OEM Customer Item Alias', {'customer': payload['customer'], 'specification': spec.name},
                          {'customer': payload['customer'], 'specification': spec.name})
    doc.customer_item_code = (payload.get('customer_item_code') or '').strip()
    doc.alias_key = digest([doc.customer, doc.customer_item_code]) if doc.customer_item_code else None
    doc.display_name, doc.favourite, doc.last_used_on = payload.get('display_name') or '', bool(payload.get('favourite')), now_datetime()
    save(doc)
    return receipt.finish({'alias': doc.name})


def list_assortment(context, cursor=0, favourites=False):
    authorize_context(context)
    filters = {'customer': context.get('customer')}
    if not context.get('customer'): frappe.throw(_('Choose a Customer for the assortment.'))
    if favourites: filters['favourite'] = 1
    results = []
    for row in frappe.get_list('OEM Customer Item Alias', filters=filters, fields=['name', 'specification', 'customer_item_code', 'display_name', 'favourite'], start=max(0, int(cursor)), page_length=30, order_by='last_used_on desc'):
        spec = frappe.get_doc('OEM Specification', row.specification)
        brand = json.loads(spec.canonical_json)['attributes']['brand']
        if context.get('brand') and context['brand'] != brand: continue
        authorize_context(dict(context, brand=brand), spec.product)
        binding, item = active_binding(spec.name, context)
        if binding:
            results.append(dict(row, product=spec.product, item_code=item.name, physical_summary=spec.summary,
                                values=json.loads(spec.canonical_json)['attributes']))
    return {'assortment': results}
