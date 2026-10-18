# Production scheduling validation

Validated on October 18, 2026 against a separate local Frappe/ERPNext v15 database (`production-test.localhost`, MariaDB on `127.0.0.1:3311`). The candidate app was loaded from its dedicated worktree. No production or shared development site was migrated or changed.

| Check | Result |
| --- | --- |
| `srv_erp.tests.test_production_scheduling` | 16 tests passed, including real DocType generation, permissions, sharing prevention, partial completion, cancellation payload protection, reassignment, standalone planner/supervisor roles and recurrence boundaries |
| `srv_erp.tests.test_stock_entry_price_list` | 7 tests passed |
| `srv_erp.tests.test_variant_attribute_edit` | 7 tests passed |
| `srv_erp.tests.test_variant_price_sync` | 3 tests passed |
| Ruff lint and formatting of new Python code | Passed |
| ESLint for changed JavaScript | Passed |
| DocType/workspace JSON and Git whitespace checks | Passed |
| Setup repeated against the same isolated database | Passed |

Chromium/Playwright smoke checks verified:

- A submitted schedule opens its assignment calendar and renders dated events with completed/target quantities.
- Record Production opens an entry, saves and submits actual variant output, and updates the assignment from 0/10 to 4/10.
- A supervisor-only user opens the Production Scheduling workspace and calendar, receives only their own events, receives HTTP 403 for another supervisor's assignment, and saves/submits production without Stock Entry privileges.
- A new custom schedule for every two weeks on Monday/Friday previews October 5, 9, 19 and 23 with total quantity 40 Nos, then saves and submits.

An independent two-connection race submitted two 6-unit drafts against the same 10-unit target. One submission succeeded; the conflicting request was rejected and still exceeded the target when retried. Final progress was 6 completed, 4 remaining. The local MariaDB has snapshot isolation enabled, so a conflict may first produce Frappe's standard concurrent-request/retry message.

## Environment limitations

The existing `test_item_group_sync` module cannot import `ERPNextTestSuite` from the installed v15 ERPNext test utilities. It did not run; the feature does not change that module. The other Item regression suites above passed.

Browser runs reported package barcode `installers` console errors in the reused bench assets. The production scheduling form, calendar, workspace, preview, entry submission and authorization checks described above completed successfully despite those asset errors. A full deployment/build was not performed.
