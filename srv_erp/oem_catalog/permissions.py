import json

import frappe
from frappe import _
from frappe.utils import getdate, today

ROLES = {'user': 'OEM Catalog User', 'approver': 'OEM Catalog Approver', 'manager': 'OEM Catalog Manager'}


def require_role(capability='user'):
    if frappe.session.user == 'Guest':
        frappe.throw(_('Sign in to use OEM Catalog.'), frappe.PermissionError)
    roles = set(frappe.get_roles())
    allowed = {ROLES[capability]} if capability != 'user' else set(ROLES.values())
    if frappe.session.user != 'Administrator' and not roles.intersection(allowed):
        frappe.throw(_('You do not have this OEM capability.'), frappe.PermissionError)


def readable(doctype, name, permission='read'):
    if not name:
        frappe.throw(_('Required context is missing.'))
    doc = frappe.get_doc(doctype, name)
    doc.check_permission(permission)
    return doc


def settings():
    return frappe.get_cached_doc('OEM Catalog Settings')


def available():
    return frappe.db.exists('DocType', 'OEM Item Binding')


def authorize_context(context, product=None, write=False, capability='user', existing=False, transaction=False):
    if not existing: require_role(capability)
    if set(context) - {'customer', 'company', 'brand', 'effective_date'}:
        frappe.throw(_('Unsupported OEM context fields.'))
    cfg = settings()
    if not existing and (cfg.mode == 'Off' or (write and cfg.mode == 'Read Only')):
        frappe.throw(_('OEM Catalog is unavailable in this mode.'), frappe.PermissionError)
    for field, doctype in (('customer', 'Customer'), ('company', 'Company'), ('brand', 'Brand')):
        if context.get(field):
            readable(doctype, context[field])
    if product and not transaction:
        readable('OEM Product', product)
    if cfg.mode == 'Pilot' and not existing:
        scopes = cfg.pilot_scope
        roles = set(frappe.get_roles())
        if not any((row.kind == 'User' and row.reference == frappe.session.user) or
                   (row.kind == 'Role' and row.reference in roles) for row in scopes):
            frappe.throw(_('You are outside the OEM pilot.'), frappe.PermissionError)
        for kind, value in (('Company', context.get('company')), ('Product', product)):
            if value and not any(row.kind == kind and row.reference == value for row in scopes):
                frappe.throw(_('This context is outside the OEM pilot.'), frappe.PermissionError)
    if cfg.require_customer_brand and context.get('customer'):
        if not context.get('brand'):
            frappe.throw(_('Choose an authorized Brand.'))
        association = frappe.db.get_value('OEM Customer Brand', {'customer': context['customer'], 'brand': context['brand'], 'enabled': 1}, ['name', 'valid_from', 'valid_until', 'approved_by'], as_dict=True)
        effective = getdate(context.get('effective_date') or today())
        if not association or not association.approved_by or (association.valid_from and effective < getdate(association.valid_from)) or (association.valid_until and effective > getdate(association.valid_until)):
            frappe.throw(_('Customer Brand association is missing or expired.'), frappe.PermissionError)
    return cfg


def request_access(request, approver=False):
    require_role('approver' if approver else 'user')
    payload = json.loads(request.submitted_payload_json)
    authorize_context(payload['context'], request.product if request.get('product') else payload['product'], capability='approver' if approver else 'user', existing=True)
    if not approver and frappe.session.user != request.requested_by and not frappe.db.exists('OEM Request Source', {'request': request.name, 'actor': frappe.session.user}):
        frappe.throw(_('Request is unavailable.'), frappe.PermissionError)
    return payload


def private_query(user=None):
    user = user or frappe.session.user
    if user == 'Administrator':
        return ''
    return '`owner` = ' + frappe.db.escape(user)


def private_permission(doc, user=None, permission_type=None):
    user = user or frappe.session.user
    if user == 'Administrator':
        return True
    if doc.doctype == 'OEM Configuration Request':
        if doc.requested_by == user or frappe.db.exists('OEM Request Source', {'request': doc.name, 'actor': user}):
            return True
        return False
    return doc.get('draft_owner') == user or doc.get('actor') == user


def deny_generic_operational_read(doc, user=None, permission_type=None):
    # Dedicated DTO endpoints enforce source/context authorization and omit
    # other customers' submitted commercial payloads. Generic exports cannot.
    return (user or frappe.session.user) == 'Administrator'
