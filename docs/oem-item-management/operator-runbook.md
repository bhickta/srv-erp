# OEM Catalog operator runbook

This PR does not authorize production activation. Keep OEM Catalog Settings in **Off**, with Item creation and both adapter flags disabled, until the release checklist is closed.

## Reproduce development checks

Use the isolated Bench under `/home/bhickta/development/oem-bench`; database port 3311, Redis 13011/11011, synthetic sites `oem-test.localhost` and `oem-dev.localhost`. Never reuse production configuration or restore a real backup for these checks. All application paths and generated files must remain under development.

The pinned tested stack is Frappe 15.111.1 (`8831f757`), ERPNext 15.111.0 (`48f6a977`), express_tally 0.2.0 (`c1537522`), Python 3.14.5, Node 24.16.0, Yarn 1.22.22. The production optional india_compliance app was not included in this synthetic stack and needs staging verification.

Run from that Bench:

```bash
env/bin/python apps/srv_erp/ops/oem/guard.py --site oem-test.localhost migrate
env/bin/python apps/srv_erp/ops/oem/guard.py --site oem-test.localhost run-tests --app srv_erp --module srv_erp.tests.oem_catalog.test_integration
env/bin/python apps/srv_erp/ops/oem/guard.py --site oem-test.localhost run-tests --app srv_erp --module srv_erp.tests.test_package_barcode
```

The guard refuses other roots/sites/database names/ports/Redis endpoints, external app paths, or enabled email/scheduler. Commands serialize through a Bench-local lock. Fixture helpers additionally require the exact synthetic test site. `ops/oem/concurrency.py` uses independent connections and commits only synthetic fixtures. `ops/oem/serve.py` serves browser tests on loopback only, without a debugger.

## Configure a pilot after review

Assign OEM Catalog User, Approver, and Manager explicitly. Retain ordinary Sales Order, Item-read, company/customer, pricing, and barcode permissions. An OEM role is not an ERPNext permission grant. Stock Manager or another existing Batch-create permission is needed for generation. The requester and approver must be different users.

Use catalogue administration to create stable Products, typed attributes/options, approved private asset revisions, fixed package factors, company defaults, and customer-brand associations. Publish the Product revision; approval requires explicit company defaults. Prices and BOMs are provisioned through ordinary reviewed ERPNext processes. No implicit variant price/BOM inheritance exists.

Begin with Read Only, then a scoped Pilot with `allow_create_items=0`. Legacy adoption requires a preview, complete per-attribute evidence, one chosen canonical Item, approval, and source fingerprint comparison. It writes OEM records only. No source Item, UOM, stock, price, or barcode is changed. Product Bootstrap currently provides suggestions only; it does not auto-import Products.

Enable creation and one adapter only after its staging gates pass. Never change a released UOM factor. Use an approved Add Transaction UOM request for an absent pair. Never create a second Item just to change a customer or ordered quantity.

## Stop and recover

Set `allow_create_items=0` to stop new Item/UOM writes. Disable adapter flags and set mode Off to stop new configuration writes. Existing concrete Items and transactions remain; do not delete/disable Items or drop OEM tables as rollback. Existing pending draft orders can be reopened and explicitly withdrawn with a reason. Preserve binding integrity guards.

A drifted binding blocks new OEM use. Quarantine through the manager command, investigate physical meaning, and follow ordinary inventory controls. Never change the Item on a released binding or repair stock automatically.

Outbox failures leave inventory decisions intact. Delivery retries are bounded and record safe error codes; inspect Failed events without copying customer payloads to public logs. No outbound email is required by the current Desk notification adapter.

Prefer a compatible forward fix. A code downgrade must retain the installed integrity controllers and namespaced metadata; an arbitrary Git revert against a newer database is not a proven rollback.
