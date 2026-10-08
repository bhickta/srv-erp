# Release checklist and current limits

The module is reviewable development code with disabled installation defaults. It is **not certified production-ready**.

Verified locally:

- Pure identity/default/rule/boundary tests.
- Real normal-user preview, request, approval, exact reuse, rollback, privacy, pending-only actual SO save/reload/submission block, barcode replay and old-endpoint denial.
- Independent 20-submit / two-approver / two-barcode-call races with one specification/request/Item/batch and preserved sources.
- Legacy barcode regression tests; JS syntax and asset build.
- Chromium configurator review at 320/360/390/412/768/1024/1440 with no dialog overflow or JS errors.
- Synthetic large-dataset query measurements and unique identity lookup plan.

Required before activation:

- Full physical Android Chrome/iOS Safari salesperson -> different approver -> Apply -> commercial submission -> barcode/download workflow, mixed orders, keyboard/zoom/focus, interrupted connection/session expiry and repeated taps. Current Chromium evidence covers configurator review only.
- Complete normal-user browser checks of manager upload/publication, association/default editors, saved drafts/orders, and adoption review.
- Full approved Apply -> normal order save -> commercial approval -> submission; last-real-row totals and tax/payment policy preservation; print/export/integration incomplete-order labeling.
- End-to-end Stock Entry, Stock Reconciliation, Delivery Note/Invoice, Purchase Receipt, Pick List, BOM/Work Order scan/quantity compatibility, historical returns/cancellation, pricing/rounding and readiness in each supported company.
- Sanitized historical transaction migration rehearsal with submitted ledger/BOM/manufacturing records, queued-job comparison, repeated migration and rollback drill. The synthetic master comparison cannot establish historical-data safety by itself.
- india_compliance and real supported integration-version checks.
- Barcode-volume and Off-mode legacy-save overhead benchmarks; full performance uncertainty/hardware manifest.
- Asset upload overwrite/export-route security tests; all User Permission/Sales Person denial cases; crash recovery, UOM-extension races, mid-batch rollback and adoption-drift concurrency.
- Named catalogue/approval/rollout/support owners, reviewed physical classifications and mappings, accounts/prices/BOM readiness, and backup/recovery verification.

Known implementation limits to review: bootstrap is suggestion-only; no automatic Product import, BOM generation, or price provisioning; legacy duplicate selection is one canonical Item per review; applicable profile validation is bounded; private operational documents use scoped API DTOs rather than unrestricted generic REST/export. Pending estimates are separate from normal order totals. Draft official print/export presentation needs its own acceptance gate.

Production deployment, activation, live adoption, legacy auto-generation setting changes, merging, and archival are operator actions outside this PR.
