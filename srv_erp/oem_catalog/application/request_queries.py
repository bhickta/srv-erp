"""Permission-aware OEM read models independent of HTTP endpoint wrappers."""
import json

import frappe

from ..permissions import request_access, require_role


def get_request_status(request):
    doc = frappe.get_doc('OEM Configuration Request', request)
    request_access(doc)
    sources = frappe.get_all('OEM Request Source', filters={'request': doc.name, 'actor': frappe.session.user}, fields=['name', 'row_intent_id', 'result_state', 'source_document'])
    result = {'api_version': 1, 'request': doc.name, 'status': doc.status, 'modified': str(doc.modified), 'reason': doc.reason, 'sources': sources}
    if doc.status == 'Approved':
        from .bindings import active_binding
        context = json.loads(frappe.get_doc('OEM Request Source', sources[0].name).context_json) if sources else json.loads(doc.submitted_payload_json)['context']
        binding, item = active_binding(doc.specification, context)
        result['item_code'] = item.name
    return result


def get_my_requests(cursor=0):
    require_role()
    rows = frappe.get_all('OEM Request Source', filters={'actor': frappe.session.user}, fields=['name', 'request', 'result_state'], start=max(0, int(cursor)), page_length=30, order_by='creation desc')
    return {'requests': [get_request_status(row.request) for row in rows]}


def get_approvals(cursor=0):
    require_role('approver')
    records = []
    for row in frappe.get_all('OEM Configuration Request', filters={'status': 'Pending'}, pluck='name', start=max(0, int(cursor)), page_length=30, order_by='requested_on asc'):
        doc = frappe.get_doc('OEM Configuration Request', row)
        try: payload = request_access(doc, approver=True)
        except frappe.PermissionError: continue
        records.append({'request': doc.name, 'modified': str(doc.modified), 'requested_by': doc.requested_by,
                        'requested_on': doc.requested_on, 'snapshot': json.loads(doc.configuration_snapshot_json)})
    return {'requests': records}

