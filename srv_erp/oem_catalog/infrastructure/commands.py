import hashlib
import json
from contextlib import contextmanager
from uuid import UUID

import frappe
from frappe.utils import now_datetime

from .documents import internal_command


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, default=str)


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def insert(doctype, **fields):
    with internal_command():
        return frappe.get_doc({'doctype': doctype, **fields}).insert(ignore_permissions=True)


def save(doc):
    with internal_command():
        return doc.save(ignore_permissions=True)


def lock(doctype, name):
    if not doctype.startswith('OEM ') and doctype != 'Item':
        raise ValueError('Unsupported lock table')
    frappe.db.sql(f'select name from `tab{doctype}` where name=%s for update', name)
    return frappe.get_doc(doctype, name)


def get_or_insert(doctype, filters, values):
    existing = frappe.db.get_value(doctype, filters, 'name')
    if existing:
        return frappe.get_doc(doctype, existing), False
    point = 'oem_insert'
    frappe.db.savepoint(point)
    try:
        return insert(doctype, **values), True
    except (frappe.DuplicateEntryError, frappe.UniqueValidationError):
        frappe.db.rollback(save_point=point)
        name = frappe.db.get_value(doctype, filters, 'name', for_update=True)
        if not name:
            raise
        return frappe.get_doc(doctype, name), False


class Receipt:
    def __init__(self, operation, uuid, payload):
        try:
            uuid = str(UUID(uuid))
        except (ValueError, TypeError, AttributeError):
            frappe.throw('INVALID_INPUT: an idempotency UUID is required')
        self.key = digest([frappe.local.site, frappe.session.user, operation, uuid])
        self.doc, created = get_or_insert('OEM Command Receipt', {'command_key': self.key},
                                         {'command_key': self.key, 'actor': frappe.session.user, 'operation': operation,
                                          'payload_hash': digest(payload), 'state': 'Processing', 'created_on': now_datetime()})
        self.doc = lock('OEM Command Receipt', self.doc.name)
        if self.doc.payload_hash != digest(payload):
            frappe.throw('IDEMPOTENCY_CONFLICT: retry payload differs')
        if not created and self.doc.state != 'Completed':
            frappe.throw('REQUEST_STATE_CONFLICT: incomplete command')
        self.replay = json.loads(self.doc.result_json) if self.doc.state == 'Completed' else None

    def finish(self, result):
        self.doc.state, self.doc.result_json = 'Completed', encoded(result)
        save(self.doc)
        return result


def audit(operation, doc, correlation, details=None):
    return insert('OEM Audit Event', actor=frappe.session.user, occurred_on=now_datetime(), operation=operation,
                  entity_type=doc.doctype, entity_name=doc.name, correlation_id=correlation,
                  after_hash=digest(doc.as_dict()), redacted_details_json=encoded(details or {}))


def notify(request, decision=False):
    insert('OEM Outbox Event', event_key=digest([request.name, request.status]), kind='Notify Decision' if decision else 'Notify Request',
           payload_json=encoded({'request': request.name}), state='Pending', next_attempt_on=now_datetime())
