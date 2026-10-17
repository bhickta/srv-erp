"""Stable API v1 adapters; policy and read models live in application services."""

import frappe
from frappe import _

from .infrastructure.api_boundary import endpoint
from .infrastructure.dto import object_input
from .permissions import readable, require_role


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
    from .application.catalogue_queries import search_products as read_model
    return read_model(context, query, cursor, limit)


@endpoint()
def get_context(source_context):
    from .application.catalogue_queries import get_context as read_model
    return read_model(source_context)


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
    from .application.request_queries import get_request_status as read_model
    return read_model(request)


@endpoint()
def get_my_requests(cursor=0):
    from .application.request_queries import get_my_requests as read_model
    return read_model(cursor)


@endpoint()
def get_approvals(cursor=0):
    from .application.request_queries import get_approvals as read_model
    return read_model(cursor)


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
    from .application.catalogue_queries import get_ui_settings as read_model
    return read_model()


@endpoint(write=True)
def quarantine_binding(binding, reason, idempotency_key):
    from .application.integrity import quarantine
    return quarantine(binding, reason, idempotency_key)


@endpoint()
def get_admin_schema(doctype):
    from .application.catalogue_queries import get_admin_schema as read_model
    return read_model(doctype)


@endpoint()
def get_admin_record(doctype, name):
    from .application.catalogue_queries import get_admin_record as read_model
    return read_model(doctype, name)


@endpoint(write=True)
def save_catalogue_record(doctype, payload, idempotency_key, name=None, expected_modified=None):
    from .application.admin import save_master
    return save_master(doctype, payload, idempotency_key, name, expected_modified)


@endpoint()
def get_saved_drafts(cursor=0):
    from .application.catalogue_queries import get_saved_drafts as read_model
    return read_model(cursor)


@endpoint()
def get_saved_orders(cursor=0):
    from .application.catalogue_queries import get_saved_orders as read_model
    return read_model(cursor)


@endpoint(write=True)
def set_customer_alias(payload, idempotency_key):
    from .application.assortment import alias
    return alias(payload, idempotency_key)


@endpoint()
def get_customer_assortment(context, cursor=0, favourites=False):
    from .application.assortment import list_assortment
    return list_assortment(object_input(context, {'customer', 'company', 'brand', 'effective_date'}), cursor, bool(favourites))
