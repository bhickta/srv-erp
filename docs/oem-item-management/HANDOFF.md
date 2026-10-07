# Start the OEM Catalog implementation in a new context

The full implementation contract is IMPLEMENTATION_PLAN.md in this directory. It defines P00-P19, schema, identity, permissions, adapters, acceptance tests, rollout, and rollback.

This planning PR contains no implementation or production operational dataset. When working on the original machine, the owner also has local copies:

- /home/bhickta/development/OEM_ITEM_MANAGEMENT_PLAN.md
- /home/bhickta/development/OEM_DEVELOPMENT_HANDOFF.md
- /home/bhickta/development/OEM_PRODUCTION_AUDIT.md (private; never commit/upload)

Launch from the development repository with the installed Codex CLI:

~~~bash
codex -C /home/bhickta/development/srv-erp --add-dir /home/bhickta/development 'Read /home/bhickta/development/OEM_DEVELOPMENT_HANDOFF.md and the full implementation plan it names. Implement P00-P19 in an isolated development worktree and test environment, keep /home/frappe read-only, and finish with reviewable PRs without merging or deploying.'
~~~

The command starts a new session with the local handoff, not an implementation in this planning worktree. Its directory options were checked against the installed codex --help. It does not bypass sandbox/approval controls or select a model. If sandbox permissions limit the development Bench/services, use the ordinary scoped permission mechanism; do not move work into production.

Portable prompt for another coding agent:

~~~text
Read docs/oem-item-management/IMPLEMENTATION_PLAN.md completely and implement its P00-P19 work packages in bhickta/srv-erp.
Fetch/pull latest version-15 and create an isolated feature worktree before editing.
Develop/build/test only under /home/bhickta/development; treat /home/frappe as read-only.
Use a synthetic isolated Frappe/ERPNext Bench with distinct databases/services and fail-closed environment guards.
Implement the independent OEM Catalog module, physical specification identity, contextual defaults, immutable assets, guided UI, atomic approval, safe legacy binding, Sales Order/barcode adapters, and full production-readiness checks.
No pending request creates an ERPNext Item. Existing stock/UOM/prices/barcodes/documents remain intact.
Customer does not split interchangeable stock; physical customization can.
Keep production data/secrets out of Git. Complete meaningful normal-user, concurrency, migration non-interference, browser, and stock scan-chain checks.
Maintain WORK_LOG.md and small focused commits; push/open PRs against version-15.
Do not merge, deploy, change production settings, or perform live adoption.
~~~

Required operator decisions in the plan are deployment gates. They do not prevent building safe defaults, editors, review tools, and synthetic end-to-end tests.
