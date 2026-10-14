import json

import frappe
from frappe.utils import add_to_date, now_datetime

from srv_erp.oem_catalog.infrastructure.commands import lock, save
from srv_erp.oem_catalog.permissions import available


def deliver_pending():
    if not available(): return
    names = frappe.get_all('OEM Outbox Event', filters={'state': ['in', ['Pending', 'Failed']], 'next_attempt_on': ['<=', now_datetime()]},
                           pluck='name', limit_page_length=50, order_by='next_attempt_on asc')
    cfg = frappe.get_cached_doc('OEM Catalog Settings')
    for name in names:
        event = lock('OEM Outbox Event', name)
        if event.state == 'Sent' or event.attempts >= cfg.notification_retry_limit: continue
        event.attempts += 1
        request = frappe.get_doc('OEM Configuration Request', json.loads(event.payload_json)['request'])
        # Notification Log is local Desk delivery; no external mail is required.
        recipients = sorted(set(frappe.get_all('OEM Request Source', filters={'request': request.name}, pluck='actor')))
        point = 'oem_notification'
        frappe.db.savepoint(point)
        try:
            for user in recipients:
                subject = frappe._('OEM request {0}: {1}').format(request.name, request.status)
                if not frappe.db.exists('Notification Log', {'for_user': user, 'subject': subject, 'document_name': request.name}):
                    frappe.get_doc({'doctype': 'Notification Log', 'for_user': user, 'type': 'Alert', 'subject': subject,
                                    'document_type': 'OEM Configuration Request', 'document_name': request.name}).insert(ignore_permissions=True)
            event.state, event.last_error_code = 'Sent', ''
        except Exception:
            frappe.db.rollback(save_point=point)
            event.state, event.last_error_code = 'Failed', 'NOTIFICATION_DELIVERY_FAILED'
            event.next_attempt_on = add_to_date(now_datetime(), minutes=min(60, 2 ** event.attempts))
        save(event)
