import hashlib
import json

import frappe
from frappe import _
from frappe.utils import now_datetime

from srv_erp.oem_catalog.domain.canonicalization import KEY, canonicalize, typed_value
from srv_erp.oem_catalog.domain.packaging import validate_packages
from srv_erp.oem_catalog.domain.rules import validate_rules
from srv_erp.oem_catalog.infrastructure.documents import internal_command
from srv_erp.oem_catalog.infrastructure.schema_reader import schema_for
from srv_erp.oem_catalog.permissions import readable, require_role

ITEM_FIELDS = {'is_purchase_item', 'is_sales_item', 'include_item_in_manufacturing', 'description', 'package_barcode_qty_entry_rule', 'valuation_method', 'inspection_required_before_purchase', 'inspection_required_before_delivery'}


def validate_company_defaults(revision):
    companies = set()
    for row in revision.company_defaults:
        readable('Company', row.company)
        if row.company in companies:
            frappe.throw(_('Duplicate company defaults.'))
        companies.add(row.company)
        for field, doctype in (('income_account', 'Account'), ('expense_account', 'Account'), ('cost_center', 'Cost Center'), ('default_warehouse', 'Warehouse')):
            if row.get(field):
                doc = readable(doctype, row.get(field))
                if doc.company != row.company or doc.get('disabled') or doc.get('is_group'):
                    frappe.throw(_('Company defaults must use active leaf records in the same company.'))


def validate_revision(revision):
    blueprint = json.loads(revision.item_blueprint_json or '{}')
    if not isinstance(blueprint, dict) or set(blueprint) - ITEM_FIELDS:
        frappe.throw(_('Item blueprint contains unsupported fields.'))
    schema, choices, packages, rules = schema_for(revision, {}, publication=True)
    keys = [a.key for a in schema.attributes]
    if not keys or len(keys) > 64 or len(keys) != len(set(keys)) or any(not KEY.fullmatch(k) for k in keys):
        frappe.throw(_('Publish between 1 and 64 attributes with unique stable keys.'))
    if not any(a.key == 'brand' and a.identity and a.required and a.kind == 'MasterLink' for a in schema.attributes):
        frappe.throw(_('Physical Brand must be a required identity master selector.'))
    for row, attr in zip(revision.attribute_definitions, schema.attributes, strict=True):
        widgets = {'Enum': {'Auto', 'Dropdown', 'SearchableSelect', 'Radio', 'Swatch'}, 'Decimal': {'Auto', 'Number'},
                   'Text': {'Auto', 'Text'}, 'Boolean': {'Auto', 'Checkbox'}, 'MasterLink': {'Auto', 'MasterPicker', 'SearchableSelect'},
                   'AssetRevision': {'Auto', 'AssetCards', 'SearchableSelect'}}
        if row.input_widget not in widgets.get(row.data_type, set()) or (row.attribute_key == 'brand' and row.allowed_master_type != 'Brand'):
            frappe.throw(_('Attribute widget or master type is invalid.'))
        if row.allowed_pattern_identifier:
            frappe.throw(_('Custom text validators are not supported.'))
        if row.default_value_json:
            typed_value(attr, json.loads(row.default_value_json))
    validate_packages(packages, schema.stock_uom)
    validate_rules(rules, schema.attributes)
    validate_company_defaults(revision)
    prior = frappe.get_all('OEM Product Revision', filters={'product': revision.product, 'state': 'Published', 'name': ['!=', revision.name]}, pluck='name')
    meaning = lambda r: {a.attribute_key: (a.data_type, a.role, a.option_set, a.allowed_master_type, a.asset_kind, a.decimal_unit, a.multi_select) for a in r.attribute_definitions}
    for name in prior:
        older = frappe.get_doc('OEM Product Revision', name)
        if older.identity_namespace == revision.identity_namespace:
            old, new = meaning(older), meaning(revision)
            if any(key not in new or new[key] != value for key, value in old.items()) or any(a.role == 'Identity' and a.attribute_key not in old for a in revision.attribute_definitions):
                frappe.throw(_('Identity meaning changes require a reviewed new namespace.'))


def validate_master(doc, old, internal):
    if doc.doctype == 'OEM Catalog Settings':
        require_role('manager')
        if not 1 <= doc.max_barcode_batch_size <= 500 or not 1 <= doc.search_page_size <= 50:
            frappe.throw(_('Invalid batch or search limit.'))
        return
    if old:
        stable = {'OEM Product': 'catalogue_code', 'OEM Option Set': 'code', 'OEM Asset': 'code'}.get(doc.doctype)
        if stable and doc.get(stable) != old.get(stable):
            frappe.throw(_('Stable catalogue codes cannot change.'))
        if old.get('state') in {'Published', 'Approved', 'Retired'}:
            before, after = old.as_dict(), doc.as_dict()
            ignored = {'modified', 'modified_by', '_comments', '_assign', '_liked_by', '__onload', 'is_current'}
            if any(before.get(k) != after.get(k) for k in before if k not in ignored):
                frappe.throw(_('Published content is immutable. Clone a new revision.'))
    if doc.doctype in {'OEM Product Revision', 'OEM Default Profile', 'OEM Asset Revision'}:
        if not internal and (doc.get('state') != (old.get('state') if old else 'Draft') or doc.get('publication_hash') or doc.get('approved_by') or doc.get('is_current')):
            frappe.throw(_('Use the publication command for state transitions.'))
    if doc.doctype == 'OEM Product Revision':
        validate_revision(doc)
    if doc.doctype == 'OEM Customer Brand':
        readable('Customer', doc.customer); readable('Brand', doc.brand)
        if not internal and (doc.enabled or doc.approved_by):
            frappe.throw(_('Use the association approval command.'))
    if doc.doctype == 'OEM Option Set':
        ids = [v.value_code for v in doc.values]
        if len(ids) != len(set(ids)) or len(ids) > 500 or any(not v or ':' in v for v in ids):
            frappe.throw(_('Option IDs must be unique stable values.'))
        if old and frappe.db.exists('OEM Attribute Definition', {'option_set': doc.name}):
            old_ids = {v.value_code for v in old.values}
            if not old_ids.issubset(set(ids)):
                frappe.throw(_('Referenced option IDs must be retired instead of removed.'))


def publish_revision(name):
    require_role('manager')
    doc = readable('OEM Product Revision', name, 'write')
    if doc.state != 'Draft':
        frappe.throw(_('Only a draft revision can be published.'))
    frappe.db.sql('select name from `tabOEM Product` where name=%s for update', doc.product)
    validate_revision(doc)
    snapshot = {key: doc.get(key) for key in ('product', 'revision', 'identity_namespace', 'stock_uom', 'item_blueprint_json')}
    for key in ('attribute_definitions', 'constraint_rules', 'company_defaults', 'packaging_choices'):
        snapshot[key] = [{k: v for k, v in row.as_dict().items() if k not in {'name', 'owner', 'creation', 'modified', 'modified_by', 'parent', 'parentfield', 'parenttype', 'docstatus', 'idx'}} for row in doc.get(key)]
    doc.publication_hash = hashlib.sha256(json.dumps(snapshot, sort_keys=True, default=str).encode()).hexdigest()
    doc.state, doc.published_by, doc.published_on = 'Published', frappe.session.user, now_datetime()
    with internal_command():
        doc.save()
        product = readable('OEM Product', doc.product, 'write')
        product.current_revision, product.lifecycle = doc.name, 'Active'
        product.save()
    return {'revision': doc.name, 'publication_hash': doc.publication_hash}


def approve_association(name, expected_modified, idempotency_key):
    from srv_erp.oem_catalog.infrastructure.commands import Receipt, audit, lock, save
    require_role('manager')
    doc = readable('OEM Customer Brand', name, 'write')
    readable('Customer', doc.customer); readable('Brand', doc.brand)
    receipt = Receipt('approve_association', idempotency_key, {'name': name, 'modified': expected_modified})
    if receipt.replay:
        return receipt.replay
    doc = lock('OEM Customer Brand', name)
    if str(doc.modified) != expected_modified:
        frappe.throw(_('STALE_CONFIGURATION: refresh the association.'))
    doc.enabled, doc.approved_by, doc.approved_on = 1, frappe.session.user, now_datetime()
    save(doc)
    audit('approve_association', doc, receipt.key)
    return receipt.finish({'association': doc.name})


def publish_profile(name, expected_modified, idempotency_key):
    from srv_erp.oem_catalog.infrastructure.commands import Receipt, audit, digest, encoded, lock, save
    require_role('manager')
    doc = readable('OEM Default Profile', name, 'write')
    if not doc.product:
        frappe.throw(_('Default profiles require an explicit Product in this release.'))
    context = {key: doc.get(key) for key in ('company', 'customer', 'brand') if doc.get(key)}
    for field, doctype in (('company', 'Company'), ('customer', 'Customer'), ('brand', 'Brand')):
        if doc.get(field): readable(doctype, doc.get(field))
    revision = readable('OEM Product Revision', readable('OEM Product', doc.product).current_revision)
    schema, _, _, _ = schema_for(revision, context)
    attributes = {a.key: a for a in schema.attributes}
    for value in doc.defaults:
        if value.attribute_key not in attributes:
            frappe.throw(_('Unknown default attribute.'))
        typed_value(attributes[value.attribute_key], json.loads(value.value_json))
    receipt = Receipt('publish_profile', idempotency_key, {'name': name, 'modified': expected_modified})
    if receipt.replay: return receipt.replay
    lock('OEM Product', doc.product)
    doc = lock('OEM Default Profile', name)
    if str(doc.modified) != expected_modified or doc.state != 'Draft':
        frappe.throw(_('STALE_CONFIGURATION: refresh the default profile.'))
    rows = frappe.get_all('OEM Default Profile', filters={'profile_code': doc.profile_code, 'is_current': 1}, pluck='name')
    for previous in rows:
        older = lock('OEM Default Profile', previous)
        older.is_current = 0
        save(older)
    doc.state, doc.is_current = 'Published', 1
    doc.publication_hash = digest([context, doc.priority, doc.valid_from, doc.valid_until, [(v.attribute_key, v.value_json, v.locked) for v in doc.defaults]])
    save(doc)
    audit('publish_profile', doc, receipt.key)
    return receipt.finish({'profile': doc.name, 'publication_hash': doc.publication_hash})
