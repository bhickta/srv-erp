"""Synthetic query-budget measurement; explicit guarded invocation only."""
import hashlib
import json
import statistics
import time

import frappe
from frappe.utils import now_datetime

from .environment import prepare


def seed_and_measure():
    prepare()
    from srv_erp.oem_catalog import api
    from srv_erp.oem_catalog.domain.canonicalization import canonicalize
    from srv_erp.oem_catalog.infrastructure.commands import digest, encoded
    from srv_erp.oem_catalog.infrastructure.schema_reader import schema_for
    from pathlib import Path
    fixture = json.loads(Path('/home/bhickta/development/oem-bench/config/race-fixture.json').read_text())
    frappe.set_user('Administrator')
    now = now_datetime()
    def bulk(doctype, columns, rows):
        metadata = ['owner', 'creation', 'modified', 'modified_by', 'docstatus']
        for offset in range(0, len(rows), 500):
            frappe.db.bulk_insert(doctype, columns + metadata,
                                 [row + ['Administrator', now, now, 'Administrator', 0] for row in rows[offset:offset+500]], ignore_duplicates=True)
    bulk('Item', ['name', 'item_code', 'item_name', 'item_group', 'stock_uom', 'is_stock_item', 'disabled', 'has_variants'],
         [[f'OEM-SYNTHETIC-LEGACY-{i:05}', f'OEM-SYNTHETIC-LEGACY-{i:05}', f'Synthetic legacy item {i}', 'Products', 'Nos', 1, 0, 0] for i in range(50000)])
    product = frappe.get_doc('OEM Product', fixture['payload']['product'])
    bulk('OEM Product', ['name', 'catalogue_code', 'display_name', 'item_group', 'lifecycle', 'current_revision'],
         [[f'OEM-SYNTHETIC-PRODUCT-{i:04}', f'SYNTHETIC-{i:04}', f'Synthetic catalogue model {i}', 'Products', 'Draft', None] for i in range(500)])
    from uuid import uuid4
    for i in range(500):
        candidate = frappe.get_doc('OEM Product', f'OEM-SYNTHETIC-PRODUCT-{i:04}')
        if candidate.current_revision: continue
        exemplar = frappe.get_doc('OEM Product Revision', product.current_revision)
        definitions = [{key: row.get(key) for key in ('attribute_key', 'label', 'data_type', 'allowed_master_type', 'role', 'required', 'input_widget')} for row in exemplar.attribute_definitions]
        copied = frappe.get_doc({'doctype': 'OEM Product Revision', 'product': candidate.name, 'revision': 1, 'identity_namespace': 'oem-v1',
            'stock_uom': 'Nos', 'item_blueprint_json': '{}', 'attribute_definitions': definitions,
            'packaging_choices': [{'code': 'unit', 'label': 'Unit', 'transaction_uom': 'Nos', 'conversion_factor': '1', 'enabled': 1}],
            'company_defaults': [{'company': fixture['payload']['context']['company']}]}).insert()
        api.publish_product_revision(copied.name, str(uuid4()), str(copied.modified))
    revision = frappe.get_doc('OEM Product Revision', product.current_revision)
    schema, _, _, _ = schema_for(revision, fixture['payload']['context'])
    specs = []
    for i in range(5000):
        identity = canonicalize(schema, {'brand': fixture['payload']['context']['brand'], 'printed_text': f'SYNTHETIC PERFORMANCE {i}'})
        specs.append([f'OEM-SYNTHETIC-SPEC-{i:05}', identity.digest, identity.canonical_json, product.name, revision.name, schema.namespace, 'Unreleased'])
    bulk('OEM Specification', ['name', 'identity_hash', 'canonical_json', 'product', 'product_revision', 'identity_namespace', 'release_state'], specs)
    def measure(fn, count=50):
        samples = []
        for _ in range(count):
            started = time.perf_counter(); fn(); samples.append((time.perf_counter() - started) * 1000)
        return {'p50_ms': round(statistics.median(samples), 3), 'p95_ms': round(sorted(samples)[int(.95*len(samples))-1], 3), 'samples': count}
    configuration = api.get_configuration(product.name, fixture['payload']['context'])
    payload = dict(fixture['payload'], configuration_token=configuration['configuration_token'])
    results = {'counts': {d: frappe.db.count(d) for d in ('Item', 'OEM Product', 'OEM Specification')},
               'product_search': measure(lambda: api.search_products(fixture['payload']['context'], 'Synthetic')),
               'configuration': measure(lambda: api.get_configuration(product.name, fixture['payload']['context'])),
               'exact_preview': measure(lambda: api.preview_configuration(payload))}
    identity = canonicalize(schema, {'brand': fixture['payload']['context']['brand'], 'printed_text': 'EXAMPLE'})
    results['identity_query_plan'] = frappe.db.sql('EXPLAIN select name from `tabOEM Specification` where identity_hash=%s', identity.digest, as_dict=True)
    Path('/home/bhickta/development/oem-bench/logs/performance.json').write_text(json.dumps(results, default=str, indent=2))
    return results
