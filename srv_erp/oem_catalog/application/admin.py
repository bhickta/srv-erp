import json

import frappe
from frappe import _

from srv_erp.oem_catalog.infrastructure.commands import Receipt
from srv_erp.oem_catalog.infrastructure.dto import object_input
from srv_erp.oem_catalog.permissions import readable, require_role

MASTERS = {'OEM Product', 'OEM Product Revision', 'OEM Option Set', 'OEM Asset', 'OEM Asset Revision', 'OEM Customer Brand', 'OEM Default Profile'}


def schema(doctype):
    require_role('manager')
    if doctype not in MASTERS: frappe.throw(_('Unsupported catalogue master.'))
    meta = frappe.get_meta(doctype)
    fields = []
    for field in meta.fields:
        if field.fieldtype in {'Section Break', 'Column Break', 'Tab Break'} or field.hidden or field.read_only: continue
        definition = {key: field.get(key) for key in ('fieldname', 'fieldtype', 'label', 'options', 'default', 'reqd')}
        if field.fieldtype == 'Table':
            definition['children'] = [{key: f.get(key) for key in ('fieldname', 'fieldtype', 'label', 'options', 'default', 'reqd')}
                                      for f in frappe.get_meta(field.options).fields if not f.read_only and not f.hidden]
        fields.append(definition)
    return {'doctype': doctype, 'fields': fields}


def save_master(doctype, payload, idempotency_key, name=None, expected_modified=None):
    require_role('manager')
    if doctype not in MASTERS: frappe.throw(_('Unsupported catalogue master.'))
    definitions = schema(doctype)['fields']
    allowed = {field['fieldname'] for field in definitions}
    payload = object_input(payload, allowed)
    receipt = Receipt('save_master', idempotency_key, {'doctype': doctype, 'payload': payload, 'name': name, 'modified': expected_modified})
    if receipt.replay:
        readable(doctype, receipt.replay['name'])
        return receipt.replay
    doc = readable(doctype, name, 'write') if name else frappe.new_doc(doctype)
    if name and str(doc.modified) != expected_modified:
        frappe.throw(_('STALE_CONFIGURATION: catalogue record changed.'))
    for definition in definitions:
        if definition['fieldtype'] != 'Table' or definition['fieldname'] not in payload: continue
        rows = payload[definition['fieldname']]
        if not isinstance(rows, list) or len(rows) > 200:
            frappe.throw(_('Too many catalogue detail rows.'))
        keys = {f['fieldname'] for f in definition['children']} | {'name'}
        for row in rows: object_input(row, keys)
    doc.update(payload); doc.save()
    return receipt.finish({'doctype': doctype, 'name': doc.name, 'modified': str(doc.modified)})
