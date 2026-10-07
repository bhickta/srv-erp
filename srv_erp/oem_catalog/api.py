import json
from functools import wraps

import frappe
from frappe import _

from .domain.models import CatalogError
from .infrastructure.dto import object_input
from .permissions import authorize_context, readable, request_access, require_role


def endpoint(write=False):
    def decorate(fn):
        @wraps(fn)
        def call(*args, **kwargs):
            if frappe.session.user == 'Guest':
                frappe.throw(_('Sign in to use OEM Catalog.'), frappe.PermissionError)
            if write: frappe.db.savepoint('oem_command_boundary')
            try:
                result = fn(*args, **kwargs)
                if isinstance(result, dict): result.setdefault('api_version', 1)
                return result
            except CatalogError as error:
                if write: frappe.db.rollback(save_point='oem_command_boundary')
                frappe.throw(_(error.code + ': ' + str(error)))
            except Exception:
                if write: frappe.db.rollback(save_point='oem_command_boundary')
                raise
        return frappe.whitelist(methods=['POST'] if write else ['GET', 'POST'])(call)
    return decorate


@endpoint()
def get_configuration(product, context):
    from .application.configure import get_configuration as configure
    return configure(product, object_input(context, {'customer', 'company', 'brand', 'effective_date'}))


@endpoint()
def preview_configuration(payload):
    from .application.configure import preview
    return preview(payload)


@endpoint()
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


@endpoint()
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


@endpoint(write=True)
def submit_configuration(payload, idempotency_key):
    from .application.request_commands import submit
    return submit(payload, idempotency_key)


@endpoint(write=True)
def approve_request(request, expected_modified, idempotency_key, reason=''):
    from .application.approve import approve
    return approve(request, expected_modified, reason, idempotency_key)


@endpoint(write=True)
def reject_request(request, expected_modified, reason, idempotency_key):
    from .application.request_commands import terminal
    return terminal(request, expected_modified, reason, idempotency_key, 'Rejected')


@endpoint(write=True)
def cancel_request(request, expected_modified, reason, idempotency_key):
    from .application.request_commands import terminal
    return terminal(request, expected_modified, reason, idempotency_key, 'Cancelled')


@endpoint(write=True)
def save_draft(payload, idempotency_key, draft=None, expected_modified=None):
    from .application.drafts import save_draft as save
    return save(payload, idempotency_key, draft, expected_modified)


@endpoint()
def get_request_status(request):
    doc = frappe.get_doc('OEM Configuration Request', request)
    request_access(doc)
    sources = frappe.get_all('OEM Request Source', filters={'request': doc.name, 'actor': frappe.session.user}, fields=['name', 'row_intent_id', 'result_state', 'source_document'])
    result = {'request': doc.name, 'status': doc.status, 'modified': str(doc.modified), 'reason': doc.reason, 'sources': sources}
    if doc.status == 'Approved':
        from .application.configure import active_binding
        context = json.loads(frappe.get_doc('OEM Request Source', sources[0].name).context_json) if sources else json.loads(doc.submitted_payload_json)['context']
        binding, item = active_binding(doc.specification, context)
        result['item_code'] = item.name
    return result


@endpoint()
def get_my_requests(cursor=0):
    require_role()
    rows = frappe.get_all('OEM Request Source', filters={'actor': frappe.session.user}, fields=['name', 'request', 'result_state'], start=max(0, int(cursor)), page_length=30, order_by='creation desc')
    return {'requests': [get_request_status(row.request) for row in rows]}


@endpoint()
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


@endpoint(write=True)
def publish_product_revision(revision, idempotency_key, expected_modified):
    from .application.publication import publish_revision
    from .infrastructure.commands import Receipt, audit
    require_role('manager')
    doc = readable('OEM Product Revision', revision, 'write')
    receipt = Receipt('publish_revision', idempotency_key, {'revision': revision, 'modified': expected_modified})
    if receipt.replay: return receipt.replay
    if str(doc.modified) != expected_modified: frappe.throw(_('STALE_CONFIGURATION: revision changed.'))
    result = publish_revision(revision)
    audit('publish_revision', frappe.get_doc('OEM Product Revision', revision), receipt.key)
    return receipt.finish(result)


@endpoint(write=True)
def approve_customer_brand(association, expected_modified, idempotency_key):
    from .application.publication import approve_association
    return approve_association(association, expected_modified, idempotency_key)


@endpoint(write=True)
def publish_default_profile(profile, expected_modified, idempotency_key):
    from .application.publication import publish_profile
    return publish_profile(profile, expected_modified, idempotency_key)


@endpoint(write=True)
def approve_asset_revision(revision, expected_modified, idempotency_key):
    from .application.assets import approve_asset
    return approve_asset(revision, expected_modified, idempotency_key)


@endpoint(write=True)
def create_import_preview(scope, kind, idempotency_key):
    from .application.adoption import preview_import
    return preview_import(scope, kind, idempotency_key)


@endpoint(write=True)
def approve_import_plan(review, expected_plan_hash, selected_rows, idempotency_key):
    from .application.adoption import approve_import
    return approve_import(review, expected_plan_hash, selected_rows, idempotency_key)


@endpoint(write=True)
def apply_import_plan(review, expected_plan_hash, idempotency_key):
    from .application.adoption import apply_import
    return apply_import(review, expected_plan_hash, idempotency_key)


@endpoint()
def validate_apply(source, document_context, row_intent_id):
    from .application.source_intents import validate_apply as validate
    return validate(source, document_context, row_intent_id)


@endpoint(write=True)
def save_pending_sales_order(order_payload, idempotency_key, expected_modified=None):
    from .application.source_intents import save_order
    return save_order(order_payload, expected_modified, idempotency_key)


@endpoint(write=True)
def generate_barcodes(specification, context, package_choice, count, idempotency_key):
    from .application.barcode_commands import generate
    return generate(specification, object_input(context, {'customer', 'company', 'brand', 'effective_date'}), package_choice, count, idempotency_key)


@endpoint()
def get_ui_settings():
    from .permissions import settings
    cfg = settings()
    roles = set(frappe.get_roles())
    permitted = frappe.session.user == 'Administrator' or bool(roles & {'OEM Catalog User', 'OEM Catalog Approver', 'OEM Catalog Manager'})
    return {'sales_order': bool(permitted and cfg.mode in {'Pilot', 'Active'} and cfg.enable_sales_order_picker),
            'barcode': bool(permitted and cfg.mode in {'Pilot', 'Active'} and cfg.enable_barcode_picker)}


@endpoint(write=True)
def quarantine_binding(binding, reason, idempotency_key):
    from .application.integrity import quarantine
    return quarantine(binding, reason, idempotency_key)
