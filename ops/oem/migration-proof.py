"""Baseline-versus-OEM migration fingerprints on a synthetic legacy-like site."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from guard import inspect

BENCH = Path('/home/bhickta/development/oem-bench')
SITE = 'oem-dev.localhost'
BASE = Path('/home/bhickta/development/srv-erp-oem-baseline')
FEATURE = Path(__file__).resolve().parents[2]
TABLES = ('Item', 'Item Variant Attribute', 'UOM Conversion Detail', 'Item Price', 'Item Attribute', 'Item Attribute Value',
          'Brand', 'Customer', 'Has Role', 'User Permission', 'Sales Person', 'Sales Order', 'Sales Order Item',
          'Delivery Note', 'Delivery Note Item', 'Sales Invoice', 'Sales Invoice Item', 'Stock Entry', 'Stock Entry Detail',
          'Stock Ledger Entry', 'Bin', 'BOM', 'BOM Item', 'Work Order', 'Package Barcode', 'Package Barcode Batch',
          'Package Barcode Scan', 'Workflow', 'Workflow Document State', 'Workflow Transition', 'ToDo')


def snapshot():
    import pymysql
    config = json.loads((BENCH / 'sites' / SITE / 'site_config.json').read_text())
    db = pymysql.connect(host='127.0.0.1', port=3311, user='_oem_dev', password=config['db_password'], database='_oem_dev', cursorclass=pymysql.cursors.DictCursor)
    results = {}
    try:
        with db.cursor() as cursor:
            for doctype in TABLES:
                cursor.execute('SHOW TABLES LIKE %s', 'tab' + doctype)
                if not cursor.fetchone(): continue
                cursor.execute(f'SELECT * FROM `tab{doctype}` ORDER BY name')
                raw = cursor.fetchall()
                ignored = {'modified', 'modified_by'}
                if doctype in {'Workflow Document State', 'Workflow Transition', 'Has Role'}: ignored |= {'name', 'creation'}
                if doctype == 'Has Role': ignored.add('idx')
                rows = [{key: value for key, value in row.items() if key not in ignored} for row in raw if not (doctype == 'Has Role' and row.get('parent') == 'Administrator')]
                # Additive transaction snapshot columns are allowed metadata.
                for row in rows:
                    for key in list(row):
                        if key.startswith('oem_'): del row[key]
                rows.sort(key=lambda row: json.dumps(row, sort_keys=True, default=str))
                results[doctype] = {'count': len(rows), 'fingerprint': hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()}
            cursor.execute("SELECT doctype,field,value FROM tabSingles WHERE doctype in ('SRV Settings','Masters Settings','Barcode Settings','Selling Settings','Stock Settings','Accounts Settings') ORDER BY doctype,field")
            results['legacy_settings'] = {'fingerprint': hashlib.sha256(json.dumps(cursor.fetchall(), sort_keys=True, default=str).encode()).hexdigest()}
    finally: db.close()
    return results


def migrate(code, label):
    env = dict(os.environ, PYTHONPATH=str(code))
    with (BENCH / 'logs' / f'migration-proof-{label}.log').open('w') as log:
        result = subprocess.run([str(BENCH / 'env/bin/python'), str(FEATURE / 'ops/oem/guard.py'), '--site', SITE, 'migrate'], env=env, cwd=BENCH, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode: raise RuntimeError(f'{label} migration failed; inspect the isolated local log')


def main():
    inspect(BENCH, SITE)
    before = snapshot()
    migrate(BASE, 'base')
    baseline = snapshot()
    migrate(FEATURE, 'oem-first')
    first = snapshot()
    migrate(FEATURE, 'oem-second')
    second = snapshot()
    baseline_changes = [key for key in before if before[key] != baseline[key]]
    additional_changes = [key for key in baseline if baseline[key] != first[key]]
    repeated_changes = [key for key in first if first[key] != second[key]]
    result = {'baseline_business_changes': baseline_changes, 'additional_oem_business_changes': additional_changes,
              'second_oem_business_changes': repeated_changes, 'tables': second,
              'limit': 'Synthetic legacy masters/UOMs/prices/barcodes; historical submitted ledger/manufacturing checks remain open. Compare semantic child content because the baseline recreates Workflow child IDs; Administrator implicit all-role metadata is excluded, while every other user grant is compared.'}
    (BENCH / 'logs/migration-proof.json').write_text(json.dumps(result, indent=2))
    print(json.dumps({key: result[key] for key in ('baseline_business_changes', 'additional_oem_business_changes', 'second_oem_business_changes', 'limit')}))
    if additional_changes or repeated_changes: raise SystemExit(1)


if __name__ == '__main__': main()
