# OEM refactor validation

Validated on 2026-10-17 against `dev` base `ba768cd`, in the dedicated
`/home/bhickta/development/srv-erp-oem-refactor` worktree. All development and
synthetic testing stayed under `/home/bhickta/development`; no production files,
schema, settings, or business data were changed.

## Results

| Check | Result |
| --- | --- |
| Python 3.14 domain/rules/boundaries + new service and API regressions | 32 passed (13 existing, 10 configuration/binding/UOM, 9 API) |
| Node 24 client-state regressions | 11 passed |
| Guarded real-database OEM integration | 9 passed, 10.324 s |
| Existing public API argument/default signatures and endpoint decorator kinds | All 31 match `origin/dev` |
| OEM Python compilation | Passed |
| OEM public/page JavaScript syntax | Passed |
| Diff whitespace | Passed |

Framework-free checks, run from this worktree:

```sh
/home/bhickta/development/oem-bench/env/bin/python -m unittest \
  srv_erp.tests.oem_catalog.test_domain \
  srv_erp.tests.oem_catalog.test_rules_defaults \
  srv_erp.tests.oem_catalog.test_boundaries \
  srv_erp.tests.oem_catalog.test_configuration_services \
  srv_erp.tests.oem_catalog.test_api_boundary -v
node --test srv_erp/tests/js/test_oem_catalog.cjs
/home/bhickta/development/oem-bench/env/bin/python -m compileall -q srv_erp/oem_catalog
for path in srv_erp/public/js/oem_catalog/*.js srv_erp/oem_catalog/page/oem_catalog/*.js; do
  node --check "$path" || exit
done
git diff --check
```

Real database checks, run from `/home/bhickta/development/oem-bench`:

```sh
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=/home/bhickta/development/srv-erp-oem-refactor \
env/bin/python /home/bhickta/development/srv-erp-oem-refactor/ops/oem/guard.py \
  --site oem-test.localhost run-tests --app srv_erp \
  --module srv_erp.tests.oem_catalog.test_integration
```

The guard verifies the exact synthetic bench/site, dedicated database and Redis
ports, disabled outbound email/scheduler, and development-only app paths. The
worktree takes precedence through `PYTHONPATH`; the bench app symlink is unchanged.
The first attempt failed all nine fixtures because of a stale Frappe module cache.
Registry inspection/cache rebuilding restored recognition of the existing OEM
Module Def; no schema migration or Module Def repair was needed. A subsequent
run passed, and the final run above passed with all Python changes present.
Bench returned zero even for the initial failed run, so the reported result is
based on its test output, not its exit status alone.

## Review and coverage

Three sub-agents audited before implementation, then implemented disjoint
backend, API, and frontend workstreams. Cross-review covered API permissions and
contracts, backend identity/binding/UOM compatibility, and frontend asynchronous
state. The architect also reviewed the diffs and ran the combined checks.

Review found a search-adapter parameter-shadowing regression during extraction.
It was fixed before commit and now has a nonempty-search forwarding regression.
The service tests cover unchanged configuration token inputs, stale tokens,
physical package validation, hash collisions, permission denials, binding drift,
locking, raw UOM factors, and stock-UOM fallback. API tests cover authentication,
verbs, versioning, rollback, bounded retries, actor filtering, and direct read
composition. Node tests use controlled asynchronous completions for brand scope,
preview/draft invalidation, and same-input retry identity; they are not browser
or physical-device UAT.

## Remaining limits and follow-ups

Existing release gates in `release-checklist.md` still apply. No claim is made of
full SRV discovery, mobile/browser UAT, historical migration rehearsal, new race
benchmarks, downstream stock/manufacturing compatibility, or live readiness.
No schema, activation default, identity rule, receipt policy, or lock order was
changed by this refactor.

Keep these existing findings for separate changes with explicit acceptance:

- Revision publication and draft-save optimistic-concurrency locking.
- Request-list duplication per source, source ordering, and missing approved binding behavior.
- HTTP `favourites` string boolean parsing and default-profile candidate filtering.
- Admin editor retry-key lifecycle.
- Catalogue page Configure waiting for brand lookup, and no-brand notices after an intervening context change.
