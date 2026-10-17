# OEM service refactor plan

## Baseline and intent

Work starts from `dev` at `ba768cd`. The original `feat/oem-item-management`
branch has no commits ahead of this base: the feature and subsequent catalogue,
customer-brand, and workspace fixes are already merged. Refactor the current
feature rather than reintroducing its original branch. Use the dedicated
`refactor/oem-services` branch and submit a PR to `dev`; do not merge or deploy.

Three independent audits cover backend architecture, correctness and testability,
and frontend/API behavior. The architect integrates their findings and reviews
contracts; implementation is delegated in disjoint areas below.

## Existing responsibilities and problems

1. `application/configure.py` combines catalogue/default loading, configuration
   tokens, identity validation, binding integrity, and preview presentation.
   Consumers unpack six- and nine-position tuples and import binding checks from
   a UI-facing configuration service. This makes changes difficult to isolate.
2. Transaction UOM lookup and comparison are repeated in request, readiness, and
   barcode paths. Preserve exact Decimal comparisons, stock-UOM fallback, and
   existing serialized factors while centralizing the policy.
3. `api.py` combines authentication, whitelisting, transaction/retry handling,
   input parsing, and database read models. Nested read endpoints cross their own
   transport boundary. Query services should be independently callable and the
   public API should remain a thin compatibility adapter.
4. Customer-brand requests can finish out of order and install a stale customer's
   brands. Configurator choice changes have inconsistent invalidation of preview,
   confirmation, and retry state. Make state transitions explicit and test them
   with controlled asynchronous completion.

## Implementation workstreams

### A. Configuration, identity, binding, and UOM services

- Introduce named immutable configuration/validation result aggregates with
  explicit fields. Separate loading and validation from preview presentation.
- Extract authoritative binding lookup/integrity/permission checks into a binding
  service. Update internal callers to use the service directly.
- Retain legacy tuple-returning helpers in `configure.py` as compatibility shims;
  internal callers use named fields instead of positional unpacking.
- Centralize framework-free UOM factor lookup/comparison and reuse it in request,
  readiness, and barcode paths. Preserve representation where responses depend
  on it; do not normalize historical values or fingerprints.
- Add focused regression tests for aggregates/compatibility, stale tokens,
  binding availability/permissions/drift, and UOM matching and fallback.

### B. API boundary and read models

- Move the endpoint decorator into infrastructure while preserving public method
  names, signatures, whitelist verbs, API version decoration, authentication,
  savepoint rollback, deadlock/timeout retries, and error translation.
- Extract catalogue/context and request read queries into application services.
  Call read services directly when composing read models.
- Keep payload parsing at a clear boundary and preserve permission checks,
  ordering, pagination, field sets, and result shapes.
- Add executable boundary tests for Guest denial, read/write verbs, versioning,
  CatalogError/unexpected failures, retry exhaustion, and read composition.

### C. Frontend request and configurator state

- Introduce a small shared latest-request guard for asynchronous brand lookup.
  Apply it to both the catalogue page and Sales Order integration. A result may
  update options only if it belongs to the current customer/context.
- Centralize invalidation when identity/package inputs change: stale preview,
  confirmation, and command state must not survive changed input. Preserve a
  command UUID when retrying the same uncertain submission.
- Add a dependency-free Node regression harness with controlled promises and
  Frappe stubs. Cover response reordering, payload allowlists, edit invalidation,
  and retry identity. Avoid a broad UI/render rewrite.

Agents own disjoint files. The API owner coordinates its imports with the backend
owner. Existing schemas, receipts, and publication state machines are outside
this refactor. Reviewers report findings first; fixes receive focused validation.

## Contract and safety invariants

- Keep API v1 endpoint paths, signatures, DTO shapes, canonical identity bytes,
  hashes, configuration tokens, and effective default/profile selection stable.
- Preserve maker-checker, context authorization, Item read permission, stock
  fingerprint checks, collision detection, and exact UOM compatibility.
- Keep Specification-before-Request lock order and actor/operation/UUID receipt
  scope. Do not add commits inside OEM code. Deadlock retry keeps its existing
  full-transaction rollback semantics.
- No schema migration, data adoption, role assignment, settings activation,
  legacy stock rewrite, or production operation. `/home/frappe` stays read only.
- Develop only under `/home/bhickta/development`; preserve existing worktrees.
- The default-profile candidate cap and full-transaction deadlock rollback are
  existing policies; their redesign requires separate requirements.

## Validation and acceptance

Baseline: 13 domain/default/rule/boundary tests pass with system Python 3.12.
Use the isolated OEM bench Python 3.14 for runtime-aligned checks. Pass the new
Python and Node regressions, existing pure suite, Python compilation, and JS
syntax checks; wire the new framework-free suites into OEM CI.

For database checks, use only the declared synthetic
`/home/bhickta/development/oem-bench/sites/oem-test.localhost` through the guarded
runner. Set `PYTHONPATH` to this refactor worktree so no app symlink changes are
needed. Run the existing OEM integration suite before/after implementation when
services are available. Record actual command results and any environment
limitations; do not substitute mocks for database acceptance claims.

Before PR, independently review the diff for compatibility/security regressions,
resolve findings, verify the base has not advanced, and rerun affected checks.
Commit the plan and focused workstreams, push, and open a reviewable PR to `dev`.
The existing release checklist still applies: passing this refactor's tests does
not certify mobile UAT, historical migration, downstream integration, or live
activation readiness.

## Audit decisions and deferred work

The read-service extraction may correct HTTP boolean parsing for the existing
`favourites` filter: strings `false` and `0` must mean false. Cover accepted true
and false values and reject unsupported values. This is an intentional API input
correction, not a response/schema change.

Keep publication locking and draft optimistic-concurrency redesign separate:
they require a dedicated concurrency design and database race tests. Also defer
request-list deduplication/source ordering, default-profile candidate filtering,
and admin-editor retry-key behavior. These findings do not justify mixing
publication lifecycle or user-visible list semantics into service extraction.
