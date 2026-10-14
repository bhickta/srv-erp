# Delivery Note UOM and barcode delivery (DN-001 / DN-002)

The implementation uses the latest production base `790a314`, rather than the
older ticket baseline `1898613`. DN-001 and DN-002 ship together because scanned
row targeting depends on the conversion and Sales Order accounting contract.

## Decisions for the ticket questions

| Question | Decision |
| --- | --- |
| DN-001 Q1: storage/display | A mapped SO row keeps its UOM: `1.5 Box`, factor `20`, stock quantity `30 Nos`. The grid quantity cell also shows the read-only stock equivalent. The quantity-entry button accepts another configured UOM and converts it into the existing row. Newly scanned rows keep the package UOM; mixed SO-linked row UOMs are supported. |
| DN-001 Q2: default UOM | Mapping from an SO keeps its SO UOM and starts at zero. A newly scanned row starts in the barcode UOM. Later scans retain that row's UOM. |
| DN-001 Q3: precision | Use the existing quantity/stock-quantity field precision. Fractional packaging quantities are permitted for DN rows and invoices made from them; whole-number stock UOM validation remains enforced. No global UOM settings are changed. |
| DN-001 Q4: returns | New quantity/reference checks and DN scan targeting skip returns; the inherited previous-document and whole-number checks remain in place for returns. |
| DN-001 Q5: row limit | No arbitrary row limit. Several rows can share one SO line. Prompt when several lines/rows are eligible; prefer a unique exact-UOM row when the SO line is unambiguous. |
| DN-002 Q1: order attribution | Prefer an existing linked DN row. If several order lines are eligible, ask before incrementing. Otherwise fetch permission-filtered pending SO lines for the same customer/company/item; select the only match or prompt. Server validation checks the row's SO parent/item/customer/company and requires references for scanned pending items. |
| DN-002 Q2: partial boxes | Assumption: one package barcode represents one complete package. Partial boxes are entered/scanned as pieces, or entered with the quantity-entry button when manual entry is allowed. No partial package-barcode quantities are introduced. |
| DN-002 Q3: duplicates | Duplicate package barcodes remain blocked across the document, regardless of row/UOM. Rapid DN scans are serialized so two pending scans cannot both accept the same barcode. |
| DN-002 Q4: prompt ownership | A shared Delivery Note scanner dialog selects the SO line and/or row UOM; both tickets use this behavior. |

An unsupported UOM is always blocked. It cannot create a second invalid row;
new rows are appropriate when there is no eligible row (including differing
warehouses/batches). Every configured UOM converts through the item stock UOM.

## Accounting and compatibility

- Reuse the package-barcode conversion primitive and recompute stock quantities before validation.
- Aggregate all rows referencing an SO detail in stock units and reject over-delivery. Lock order documents and their children in a stable order before reading pending quantities.
- ERPNext normally sums raw DN quantities for SO delivered counters. The DN controller instead expresses each source stock quantity in the SO line UOM. The stock-invoice controller uses the same calculation when it recounts existing DNs.
- Preserve customer/company/project/currency/item comparisons. Only SO UOM matching is relaxed for convertible DN rows, and for invoices mapped from them. Existing Sales Invoice/DN row UOM comparisons remain enforced.
- Compare SO rates per stock unit while preserving the persisted row rate.
- Force Barcode Only compares the sum of DN stock quantities with the converted scans, rather than copying the scan count into every same-item row. With several rows, operators keep the allocation; the server rejects a mismatched total.
- The production branch keeps its newer removal of the blanket SO-reference rule. The new scan-specific rule does not reinstate it for unrelated manual deliveries. The dev branch preserves its existing blanket reference hook and OEM hooks.
- Existing Stock Entry/Reconciliation scan paths continue to delegate to ERPNext. Two pre-existing test issues were repaired: the unavailable v16 test-suite import on v15 and dictionary `items` attribute access. The precision helper now checks that `precision` is callable for dictionary test rows.

No new fields or schema migration are required. Deployment requires the normal
asset build, cache clear, and application process restart so controller/hook
changes load. Neither PR deploys or merges itself.

## Validation

Tests run on ERPNext `15.111.0` / Frappe v15 using a disposable development DB
clone on local MariaDB port `3311`. The production check uses its own site
`dn-uom-test.localhost`; OEM child-link metadata was removed only from that clone
because the production branch has no OEM module. Shared dev/production sites
were not migrated. Test fixtures are synthetic and include a normal operator
`dn-operator@example.com`.

The isolated bench is `/home/bhickta/development/dn-test-bench`. Its `run-check.py`
sets the candidate app/dependency import paths and runs Frappe's bench helper
from that bench's sites directory. These are the executed equivalents of the
ticket's bench commands:

```sh
PYTHONDONTWRITEBYTECODE=1 /home/bhickta/development/oem-bench/env/bin/python \
  /home/bhickta/development/dn-test-bench/run-check.py --site dn-uom-test.localhost \
  run-tests --app srv_erp --module srv_erp.tests.test_delivery_note_uom_conversion --skip-test-records
# Ran 19 tests in 43.971s / OK
PYTHONDONTWRITEBYTECODE=1 /home/bhickta/development/oem-bench/env/bin/python \
  /home/bhickta/development/dn-test-bench/run-check.py --site dn-uom-test.localhost \
  run-tests --app srv_erp --module srv_erp.tests.test_package_barcode --skip-test-records
# Ran 15 tests in 1.571s / OK
PYTHONDONTWRITEBYTECODE=1 /home/bhickta/development/oem-bench/env/bin/python \
  /home/bhickta/development/dn-test-bench/run-check.py --site dn-uom-test.localhost \
  run-tests --app srv_erp --module srv_erp.tests.test_delivery_note_sales_order_reference --skip-test-records
# Ran 9 tests in 0.061s / OK
node --test srv_erp/tests/js/test_delivery_note_scanner.cjs
# tests 18 / pass 18 / fail 0
PYTHONDONTWRITEBYTECODE=1 /home/bhickta/development/oem-bench/env/bin/python \
  /home/bhickta/development/dn-test-bench/run-check.py build --app srv_erp
# DONE Total Build Time: 163.751ms / Done in 1.09s. / Compiling translations for srv_erp
```

Targeted Ruff checks, JavaScript syntax checks, and `git diff --check` are also run.
The ERP integration tests cover decimal packaging, whole stock units, mixed rows,
exact/over-delivery, pending quantities, zero drafts/submission, reference
integrity/permissions, submit/cancel status, DN invoices, later stock invoices,
and inventory bin quantity changes. The Node suite covers UOM stickiness,
reference assignment/prompts, unknown UOM, warehouse matching, duplicate/rapid
scans, converted quantity enforcement, scan review, returns and scanner delegation.
Browser manual acceptance has not been run; these are executable integration
and scanner tests, not a claim of a browser walkthrough.

Final production-base integration output (raw excerpt):

```text
.
----------------------------------------------------------------------
Ran 19 tests in 43.971s

OK
```
