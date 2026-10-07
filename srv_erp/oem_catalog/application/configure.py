import json

import frappe
from frappe import _
from frappe.utils import getdate, today

from srv_erp.oem_catalog.domain.canonicalization import canonicalize
from srv_erp.oem_catalog.domain.defaults import Default, resolve
from srv_erp.oem_catalog.domain.fingerprints import fingerprint
from srv_erp.oem_catalog.domain.rules import apply_rules
from srv_erp.oem_catalog.infrastructure.commands import digest
from srv_erp.oem_catalog.infrastructure.dto import configuration_input
from srv_erp.oem_catalog.infrastructure.schema_reader import schema_for
from srv_erp.oem_catalog.permissions import authorize_context, readable


def load_configuration(product_name, context):
    authorize_context(context, product_name)
    product = readable('OEM Product', product_name)
    if product.lifecycle != 'Active' or not product.current_revision:
        frappe.throw(_('Product is not published.'))
    revision = readable('OEM Product Revision', product.current_revision)
    if revision.product != product.name or revision.state != 'Published':
        frappe.throw(_('Product revision is not published.'))
    schema, choices, packages, rules = schema_for(revision, context)
    defaults = []
    for row in revision.attribute_definitions:
        if row.default_value_json:
            defaults.append(Default(row.attribute_key, json.loads(row.default_value_json), 'product_revision', revision.name, revision.revision, locked=bool(row.default_locked)))
    profile_hashes = []
    effective = getdate(context.get('effective_date') or today())
    filters = {'state': 'Published', 'is_current': 1}
    names = frappe.get_list('OEM Default Profile', filters=filters, or_filters=[['product', '=', product.name], ['product', 'is', 'not set']], pluck='name', limit_page_length=201)
    if len(names) > 200: frappe.throw(_('CONFIGURATION_CONFLICT: too many applicable default profiles.'))
    for name in names:
        profile = readable('OEM Default Profile', name)
        if profile.product and profile.product != product.name: continue
        if any(profile.get(key) and profile.get(key) != context.get(key) for key in ('company', 'customer', 'brand')):
            continue
        if (profile.valid_from and effective < getdate(profile.valid_from)) or (profile.valid_until and effective > getdate(profile.valid_until)):
            continue
        if profile.item_group:
            group = readable('Item Group', profile.item_group)
            actual = readable('Item Group', product.item_group)
            if not (group.lft <= actual.lft and group.rgt >= actual.rgt): continue
        scope = ('customer_brand_product' if profile.customer and profile.product else 'customer_brand' if profile.customer else
                 'brand_product' if profile.brand and profile.product else 'brand_group' if profile.brand and profile.item_group else
                 'brand' if profile.brand else 'company' if profile.company else 'product_revision')
        profile_hashes.append(profile.publication_hash)
        for row in profile.defaults:
            defaults.append(Default(row.attribute_key, json.loads(row.value_json), scope, profile.name, profile.revision, specificity=(group.lft if profile.item_group else 0), priority=profile.priority, locked=bool(row.locked), explanation=row.explanation or ''))
    if context.get('brand'):
        defaults.append(Default('brand', context['brand'], 'source', 'Context', locked=True))
    provenance = resolve(defaults)
    token = digest([frappe.local.site, product.name, revision.publication_hash, sorted(profile_hashes), context, str(effective), choices, 'oem-adapter-v1'])
    return product, revision, schema, choices, packages, rules, defaults, provenance, token


def get_configuration(product, context):
    record, revision, schema, choices, packages, rules, defaults, provenance, token = load_configuration(product, context)
    fields = []
    for row in revision.attribute_definitions:
        fields.append({key: row.get(key) for key in ('attribute_key', 'label', 'description', 'data_type', 'role', 'input_widget', 'required', 'decimal_precision', 'min_value', 'max_value', 'increment', 'multi_select')}
                      | {'options': choices[row.attribute_key], 'default': provenance.get(row.attribute_key)})
    return {'api_version': 1, 'product': product, 'display_name': record.display_name, 'revision': revision.name,
            'fields': fields, 'packages': [{'code': p.code, 'label': next(r.label for r in revision.packaging_choices if r.code == p.code), 'uom': p.uom, 'factor': str(p.factor), 'stock_uom': schema.stock_uom} for p in packages],
            'configuration_token': token, 'rules': rules}


def validated(payload):
    payload = configuration_input(payload)
    product, revision, schema, choices, packages, rules, defaults, provenance, token = load_configuration(payload['product'], payload['context'])
    if payload.get('configuration_token') != token:
        frappe.throw(_('STALE_CONFIGURATION: reload configuration and preserve your choices.'))
    explicit = [Default(key, value, 'user', 'You') for key, value in payload['values'].items()]
    provenance = resolve(defaults + explicit)
    values = {key: row['value'] for key, row in provenance.items()}
    identity = canonicalize(schema, values)
    apply_rules(rules, identity.values, schema.attributes)
    for attribute in schema.attributes:
        if attribute.kind == 'AssetRevision' and attribute.key in identity.values:
            from .assets import verified_bytes
            verified_bytes(readable('OEM Asset Revision', identity.values[attribute.key]), payload['context'])
    package = next((p for p in packages if p.code == payload.get('package_choice')), None)
    if not package:
        frappe.throw(_('INVALID_INPUT: choose an approved package.'))
    row = next(r for r in revision.packaging_choices if r.code == package.code)
    if row.physical_pack_value and identity.values.get('physical_pack') != row.physical_pack_value:
        frappe.throw(_('CONFIGURATION_CONFLICT: packaging does not match physical stock.'))
    return payload, product, revision, identity, provenance, package


def active_binding(specification, context, permission=True, current=False):
    name = frappe.db.get_value('OEM Item Binding', {'specification': specification}, 'name', for_update=current)
    if not name: return None, None
    binding = frappe.get_doc('OEM Item Binding', name, for_update=current)
    if binding.binding_state != 'Active':
        frappe.throw(_('ITEM_DRIFT: binding is unavailable.'))
    item = frappe.get_doc('Item', binding.stock_item, for_update=current)
    if permission: item.check_permission('read')
    if item.disabled or item.has_variants:
        frappe.throw(_('DISABLED_MATCH: exact Item is unavailable.'))
    if fingerprint(item.as_dict()) != binding.expected_stock_fingerprint:
        frappe.throw(_('ITEM_DRIFT: stock identity changed.'))
    return binding, item


def preview(payload):
    payload, product, revision, identity, provenance, package = validated(payload)
    specification = frappe.db.get_value('OEM Specification', {'identity_hash': identity.digest}, ['name', 'canonical_json'], as_dict=True)
    binding, item = (None, None)
    if specification:
        if specification.canonical_json != identity.canonical_json:
            frappe.throw(_('CONFIGURATION_CONFLICT: identity collision.'))
        binding, item = active_binding(specification.name, payload['context'])
    from .readiness import readiness
    return {'api_version': 1, 'outcome': 'EXISTING' if binding else 'MISSING', 'identity_hash': identity.digest,
            'summary': product.display_name, 'values': identity.values, 'provenance': provenance,
            'item_code': item.name if item else None, 'specification': specification.name if specification else None,
            'package': {'code': package.code, 'uom': package.uom, 'factor': str(package.factor), 'stock_uom': revision.stock_uom},
            'readiness': readiness(item, revision, payload['context'], package) if item else {'physical': False, 'sales': False, 'barcode': False, 'manufacturing': False}}
