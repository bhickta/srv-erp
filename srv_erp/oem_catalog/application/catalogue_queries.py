"""Permission-aware OEM read models independent of HTTP endpoint wrappers."""
import json

import frappe
from frappe import _

from ..infrastructure.dto import object_input
from ..permissions import authorize_context, readable, require_role


def search_products(context, query='', cursor=0, limit=30):
    context = object_input(context, {'customer', 'company', 'brand', 'effective_date'})
    cfg = authorize_context(context)
    cursor, limit = int(cursor), min(int(limit), 50)
    if cursor < 0 or limit < 1 or len(query) > 100:
        frappe.throw(_('INVALID_INPUT: search bounds exceeded.'))
    filters = {'lifecycle': 'Active'}
    if cfg.mode == 'Pilot':
        filters['name'] = ['in', [r.reference for r in cfg.pilot_scope if r.kind == 'Product']]
    query_filters = [['display_name', 'like', '%' + query + '%'], ['catalogue_code', 'like', '%' + query + '%'], ['search_terms', 'like', '%' + query + '%']] if query else None
    rows = frappe.get_list('OEM Product', filters=filters, or_filters=query_filters, fields=['name', 'catalogue_code', 'display_name', 'item_group', 'image', 'description'], start=cursor, page_length=limit, order_by='catalogue_code asc')
    return {'products': rows, 'next_cursor': cursor + len(rows) if len(rows) == limit else None}


def get_context(source_context):
    context = object_input(source_context, {'customer', 'company', 'brand', 'effective_date'})
    require_role()
    for key, doctype in (('customer', 'Customer'), ('company', 'Company')):
        if context.get(key): readable(doctype, context[key])
    brands = []
    if context.get('customer'):
        from frappe.utils import getdate, today
        date = getdate(context.get('effective_date') or today())
        for row in frappe.get_list('OEM Customer Brand', filters={'customer': context['customer'], 'enabled': 1}, fields=['brand', 'valid_from', 'valid_until', 'default_for_customer', 'approved_by'], limit_page_length=500):
            if row.approved_by and (not row.valid_from or date >= getdate(row.valid_from)) and (not row.valid_until or date <= getdate(row.valid_until)):
                brand = frappe.get_doc('Brand', row.brand)
                if brand.has_permission('read'): brands.append({'value': brand.name, 'label': brand.name, 'default': row.default_for_customer})
    return {'brands': brands}


def get_ui_settings():
    from ..permissions import settings
    cfg = settings()
    roles = set(frappe.get_roles())
    permitted = frappe.session.user == 'Administrator' or bool(roles & {'OEM Catalog User', 'OEM Catalog Approver', 'OEM Catalog Manager'})
    return {'sales_order': bool(permitted and cfg.mode in {'Pilot', 'Active'} and cfg.enable_sales_order_picker),
            'barcode': bool(permitted and cfg.mode in {'Pilot', 'Active'} and cfg.enable_barcode_picker),
            'require_customer_brand': bool(cfg.require_customer_brand)}


def get_admin_schema(doctype):
    from .admin import schema
    return schema(doctype)


def get_admin_record(doctype, name):
    from .admin import schema
    schema(doctype)
    return readable(doctype, name, 'write').as_dict()


def get_saved_drafts(cursor=0):
    require_role()
    rows = frappe.get_all('OEM Configuration Draft', filters={'draft_owner': frappe.session.user},
                    fields=['name', 'product_revision', 'context_json', 'values_json', 'modified'], start=max(0, int(cursor)), page_length=30, order_by='modified desc')
    for row in rows: row['product'] = frappe.db.get_value('OEM Product Revision', row.product_revision, 'product')
    return {'drafts': rows}


def get_saved_orders(cursor=0):
    require_role()
    return {'orders': frappe.get_list('Sales Order', filters={'docstatus': 0, 'oem_order_entry_enabled': 1},
                    fields=['name', 'customer', 'oem_configuration_status', 'oem_unresolved_line_count', 'modified'], start=max(0, int(cursor)), page_length=30, order_by='modified desc')}
