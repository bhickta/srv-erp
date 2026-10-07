import json
from uuid import UUID

import frappe
from frappe import _

CONFIG_KEYS = {'api_version', 'product', 'configuration_token', 'values', 'package_choice', 'context', 'source'}
SOURCE_KEYS = {'adapter', 'doctype', 'field', 'document', 'row_intent_id', 'modified'}


def object_input(value, keys, limit=128 * 1024):
    if isinstance(value, str):
        if len(value.encode()) > limit:
            frappe.throw(_('INVALID_INPUT: payload is too large.'))
        try: value = json.loads(value)
        except (ValueError, TypeError): frappe.throw(_('INVALID_INPUT: expected JSON.'))
    if not isinstance(value, dict) or set(value) - keys or len(json.dumps(value).encode()) > limit:
        frappe.throw(_('INVALID_INPUT: unexpected or oversized fields.'))
    return value


def configuration_input(payload):
    payload = object_input(payload, CONFIG_KEYS)
    if payload.get('api_version') != 1 or not isinstance(payload.get('product'), str) or not isinstance(payload.get('values'), dict):
        frappe.throw(_('INVALID_INPUT: invalid configuration.'))
    payload['context'] = object_input(payload.get('context'), {'customer', 'company', 'brand', 'effective_date'})
    payload['source'] = object_input(payload.get('source', {}), SOURCE_KEYS)
    source = payload['source']
    if source.get('adapter', 'standalone') not in {'standalone', 'sales_order', 'barcode'}:
        frappe.throw(_('INVALID_INPUT: unsupported source adapter.'))
    if source.get('adapter') == 'sales_order':
        if source.get('doctype') != 'Sales Order' or source.get('field') != 'items':
            frappe.throw(_('INVALID_INPUT: unsupported source document.'))
        try: UUID(source.get('row_intent_id', ''))
        except (ValueError, TypeError, AttributeError): frappe.throw(_('INVALID_INPUT: row intent UUID is required.'))
        if source.get('document'):
            doc = frappe.get_doc('Sales Order', source['document'])
            doc.check_permission('write')
            if doc.docstatus != 0 or doc.customer != payload['context'].get('customer') or doc.company != payload['context'].get('company'):
                frappe.throw(_('FORBIDDEN: source order context is invalid.'), frappe.PermissionError)
        elif not frappe.has_permission('Sales Order', 'create'):
            frappe.throw(_('FORBIDDEN: Sales Order creation is unavailable.'), frappe.PermissionError)
    return payload
