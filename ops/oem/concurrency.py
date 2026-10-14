"""Real independent-connection races; only run on the guarded synthetic Bench."""
import json
import multiprocessing as mp
import os
from pathlib import Path
import sys
import time
from uuid import uuid4

from guard import inspect

BENCH = Path('/home/bhickta/development/oem-bench')
SITE = 'oem-test.localhost'


def worker(kind, fixture, queue, barrier):
    import frappe
    from srv_erp.oem_catalog import api
    frappe.init(site=SITE, sites_path=str(BENCH / 'sites'))
    frappe.connect()
    try:
        if kind == 'submit': frappe.set_user(fixture['requester'])
        elif kind == 'approve': frappe.set_user(fixture['actor'])
        else: frappe.set_user('oem-barcode@example.com')
        barrier.wait(timeout=40)
        started = time.monotonic()
        if kind == 'submit':
            payload = dict(fixture['payload'], source={'adapter': 'standalone', 'row_intent_id': str(uuid4())})
            result = api.submit_configuration(payload, str(uuid4()))
        elif kind == 'approve':
            result = api.approve_request(fixture['request'], fixture['modified'], str(uuid4()))
        else:
            result = api.generate_barcodes(fixture['specification'], fixture['payload']['context'], 'unit', 2, fixture['barcode_key'])
        frappe.db.commit()
        queue.put({'ok': True, 'result': result, 'seconds': time.monotonic() - started})
    except Exception as error:
        frappe.db.rollback()
        queue.put({'ok': False, 'error': type(error).__name__, 'message': str(error)[:250]})
    finally: frappe.destroy()


def race(kind, fixtures):
    context = mp.get_context('spawn')
    queue = context.Queue()
    barrier = context.Barrier(len(fixtures))
    processes = [context.Process(target=worker, args=(kind, fixture, queue, barrier)) for fixture in fixtures]
    for process in processes: process.start()
    results = [queue.get(timeout=90) for _ in processes]
    for process in processes: process.join(timeout=10)
    if any(not result['ok'] for result in results):
        raise RuntimeError(json.dumps(results))
    return [result['result'] for result in results]


def main():
    inspect(BENCH, SITE)
    os.chdir(BENCH / 'sites')
    fixture = json.loads((BENCH / 'config/race-fixture.json').read_text())
    submits = race('submit', [fixture] * 20)
    assert len({r['specification'] for r in submits}) == 1
    assert len({r['request'] for r in submits}) == 1
    import frappe
    frappe.init(site=SITE, sites_path=str(BENCH / 'sites')); frappe.connect(); frappe.set_user('Administrator')
    request = frappe.get_doc('OEM Configuration Request', submits[0]['request'])
    assert frappe.db.count('OEM Request Source', {'request': request.name}) == 20
    approval = dict(fixture, request=request.name, modified=str(request.modified))
    frappe.destroy()
    approvals = race('approve', [dict(approval, actor=fixture['approver']), dict(approval, actor='oem-approver-two@example.com')])
    assert len({r['item_code'] for r in approvals}) == 1
    barcode_fixture = dict(fixture, specification=submits[0]['specification'], barcode_key=str(uuid4()))
    generations = race('barcode', [barcode_fixture] * 2)
    assert generations[0]['batch'] == generations[1]['batch']
    frappe.init(site=SITE, sites_path=str(BENCH / 'sites')); frappe.connect()
    assert frappe.db.count('OEM Item Binding', {'specification': submits[0]['specification']}) == 1
    assert frappe.db.count('Package Barcode', {'generation_batch': generations[0]['batch']}) == 2
    assert frappe.db.count('OEM Command Receipt', {'state': 'Processing'}) == 0
    frappe.destroy()
    print(json.dumps({'simultaneous_submits': 20, 'specifications': 1, 'active_requests': 1, 'preserved_sources': 20,
                      'simultaneous_approvals': 2, 'items': 1, 'barcode_retries': 2, 'batches': 1, 'labels': 2, 'processing_receipts': 0}))


if __name__ == '__main__': main()
