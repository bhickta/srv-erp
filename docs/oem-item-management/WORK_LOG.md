# OEM item management execution log

Objective: deliver the OEM Catalog implementation and final PR to `dev`, without deployment or production changes.

Constraints: development only under `/home/bhickta/development`; `/home/frappe` read only; synthetic isolated services only; preserve existing Items, quantities, prices, UOMs, barcodes, and commercial workflows. No planning/private audit artifacts in Git. No merge or activation.

Baseline: `origin/dev` and `origin/version-15` both `a41f98875c8f874819051eed6b01980fe114a1b8`. Fresh worktree `srv-erp-oem`, branch `feat/oem-item-management`, fetched and pulled with `--ff-only`.

Current package: P00, environment and baseline.

Environment: dedicated `oem-bench`, MariaDB 3311, Redis cache 13011 / queue 11011, HTTP 8011; synthetic sites `oem-dev.localhost` / `oem-test.localhost`. Existing development replica is not used as a test database. Declared `express_tally` dependency will be installed from its real source.

Next actions:
1. Finish dedicated service/site setup and record dependency versions.
2. Run baseline legacy tests through the fail-closed guard.
3. Implement contracts and pure domain before persistence/UI.

Release evidence: not yet established. Physical Android/iOS UAT requires operator execution; emulation alone cannot close that gate.

Completed P01-P03 outputs: architecture/API contracts, pure canonicalization, typed attributes, fixed packages, transitions, fingerprints, bounded rules, defaults/provenance. Unit command `python3 -m unittest discover -s srv_erp/tests/oem_catalog -v`: 10 passing. Commits 964a37b, e857969, c67bb3d. P00 guard committed 05a7dac; isolated stack setup still in progress, so baseline integration evidence is pending.

Current package P04/P05: additive schemas and protected publication. Generated metadata creates no business catalogue records. Role definitions have no user grants. Only namespaced SO/row/batch Custom Fields are added. Database install/migration checks remain pending.

P05: governed Product revision validation/publication, immutable approved private File checks, explicit customer-brand association approval, and Product-scoped default profile publication. Broader default profile scopes remain a documented unsupported path until their publication overlap checks are proven. P06: scoped role/context helpers and private generic REST permission hooks. Receipts use savepoint-protected database uniqueness and same-transaction completion; no manual commit. Integration validation pending clean installation.

Clean-install prerequisite found on the pinned baseline: Frappe `init_singles` runs before SRV `after_install`, but SRV Settings has mandatory `variant_auto_create_attribute=Brand` before that Item Attribute exists. A narrow `before_install` creates the missing empty Brand attribute on a clean installation only. Existing installs/migrations never execute this hook; no variant creation or Brand save occurs.

P07-P10 committed: b97819b scoped search/configuration/preview, 86ec6de private drafts and requests, c53c41c atomic Item materialization and separate readiness. Runtime tests are pending and these capabilities are not marked production-ready.

P11-P15 implementation commits: 9ff6a32 explicit evidence/fingerprint legacy adoption; ead5a90 pending Sales Order child persistence/controller exception; 01d890c shared typed configurator; 450093d managed barcode generation/download and focused Item/downstream checks. Line-card form presenter and runtime acceptance tests are in progress. Catalogue manager mobile editors, customer assortments, manufacturing evidence, UOM extension workflow, protected print/export review, and performance/concurrency evidence remain incomplete; do not infer completion from these package numbers.

Environment notes: Frappe 15.111.1 `8831f757`, ERPNext 15.111.0 `48f6a977`, express_tally 0.2.0 `c1537522`, Python 3.14.5, Node 24.16.0, Yarn 1.22.22. Real declared dependency installed. OEM migration succeeded after synthetic legacy prerequisite managers. Existing tests imported a nonexistent `ERPNextTestSuite`; 36f210c updates four test classes to pinned `FrappeTestCase`. Test site is exclusively synthetic; no restored database or production configuration was used.

P16: transactional OEM outbox with bounded, idempotent Desk Notification Log delivery and retry; explicit manager quarantine command. Notifications are outside the approval transaction. No automatic Item repair. Retry worker remains disabled on the synthetic site. Generic workflow REST/export reads are denied for non-Administrator users; scoped API DTOs provide authorized views without disclosing another source's customer payload.
