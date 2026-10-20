# Production scheduling validation

## Original version-15 checks

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

## Original validation limitations

The existing `test_item_group_sync` module cannot import `ERPNextTestSuite` from the installed v15 ERPNext test utilities. It did not run; the feature does not change that module. The other Item regression suites above passed.

Browser runs reported package barcode `installers` console errors in the reused bench assets. The production scheduling form, calendar, workspace, preview, entry submission and authorization checks described above completed successfully despite those asset errors. A full deployment/build was not performed.

## Dev branch port

The implementation was ported onto `dev` at `ba768cd` and validated separately on `production-dev-test.localhost`, cloned into a new local database from the isolated dev test fixture. Application schema synchronization and production-role/field setup passed.

- All 16 production scheduling tests passed with the dev branch's OEM hooks active.
- All 17 Stock Entry price, variant attribute and variant price regression tests passed.
- All 13 OEM domain/rules/boundary checks passed.
- Compared the merged hook configuration with the unmodified dev baseline: every pre-existing permission hook, document event, class/method override and migration hook remains present. Production permission maps extend the existing maps.
- Ruff lint and Git whitespace checks passed.

The dev Item Group suite ran seven tests with two errors in template-to-variant field/group synchronization. Both errors were reproduced against unmodified `dev` (`ba768cd`) on the same isolated database, confirming an existing baseline issue. The five other tests passed. Browser and concurrency results above describe the original implementation; they were not repeated for this hook-preserving port.

## Multi-item schedules and mapped production entries

Validated the multi-item revision on the separate `production-items-test.localhost` database, cloned from the original single-item feature test site. No shared development or production site was changed.

- **30 production tests passed**, including all 16 original tests plus multi-item generation, exact variant enforcement, template output split across variants, native mapped entry creation, selected-row mapping, pending quantities, percentage/status transitions, cancellation reversal, source tampering, supervisor filtering and legacy migration idempotency.
- Child-table API checks cover lists, direct reads and value fetching, along with blocked row sharing. The child controllers resolve their actual parent document for Frappe v15's document-level permission checks; row queries also enforce the parent scope.
- The 17 Item/Stock Entry regressions and 13 OEM domain/rules/boundary checks passed.
- A comparison of the original and upgraded databases verified preservation of seven original schedules, 12 dated assignments and 10 production entries: names, document status, planned/submitted quantities and progress were retained, with source rows and percentages backfilled.
- The two-connection submission race still allowed only one 6-unit submission against a 10-unit target; the conflicting request could not produce beyond the remaining target on retry.
- Ruff, ESLint and Git whitespace checks passed.

Chromium exercised the form workflow at 1600px and inspected the responsive form at 390px: create two variant rows under a selected template, verify the template-filtered variant picker, preview, save/submit, use Create → Production Entry, receive pending quantities 10 and 20, submit 5 and 20, and observe Partly Produced / 75% / one item line remaining. A supervisor then opened the pending calendar assignment, mapped the remaining five units without re-entering source data, submitted them, and the parent reached Completed / 100% / zero item lines remaining. Screenshots were inspected to remove internal column labels and confirm compact header sections and full-width item tables.

Overall completion is deliberately the mean completion of dated item assignments, rather than a sum of unlike UOMs. One entry groups only one supervisor's assignments. If a later reassignment splits a grouped entry's current ownership, supervisors cannot access that mixed-ownership entry; planners retain the complete history.

## Item dates, names and multiple work responsibilities (October 20, 2026)

Validated separate candidates based on `version-15` (`319c002`) and `dev` (`8013e48`) using isolated local databases on port 3311. Production includes the multi-item prerequisites already present on dev. No shared development or production site was changed.

- **39 production tests passed on each branch**, including independent fabrication/bending balances and statuses, supervisor privacy, one user with several work areas, source-derived item names and dates, item recurrence anchors, date bounds, responsibility validation, immutable submitted sources, child-table access and sharing, cancellation and repeatable migration.
- Moving one operation to a later date preserves its original physical occurrence: the planned quantity stays unchanged, the entry uses the revised source date, and finished quantity still requires every responsibility.
- **17 Stock Entry/variant regression tests passed on each branch**. All **13 OEM domain/rules/boundary tests passed on dev**, with existing OEM hooks preserved.
- The original seven schedules, 12 assignments and 10 entries retained their names, source links, document states and quantities after upgrading the production fixture. The migration backfills names, dates and the default Production work area without creating extra assignments or explicit responsibilities.
- Ruff, ESLint, JavaScript syntax and Git whitespace checks passed.

Chromium exercised the schedule and entry workflow on both candidates. Header-date changes updated rows using the old default while preserving a manual item-date override. The preview listed both work areas; the Create dialog updated available work areas when the supervisor changed. Mapped entries showed Item Code, Item Name and Schedule Date together. Fabrication submission left bending fully pending and showed 50% overall work completion with zero finished units. The bending supervisor saw only their own assignments and received HTTP 403 for the fabrication entry. Record Production inherited bending dates and quantities; submitting both remaining assignments completed the schedule at 100%. Desktop (1600px) and mobile (390px) forms were captured for inspection.

The reused production test bench still reports the previously documented barcode `installers` asset error. Scheduling actions completed successfully. These checks used a local Frappe/ERPNext v15 runtime; deployment and migration on the live sites remain part of release installation.

## Work Area / Operation links (October 20, 2026)

Work Area / Operation now links to ERPNext's Operation master on responsibility rows, assignments, entry headers and entry items. The mapped-entry dialog uses an Operation Link filtered to the selected supervisor's pending operations. Production roles receive Operation selection permission. Migration creates missing Operation records for historical work-area text and the default Production operation, preserving source names, quantities and assignments.

All **41 production tests passed on each branch**, including new checks for all four Link definitions, rejection of nonexistent operations, supervisor link search permission and idempotent conversion of existing text labels. Chromium exercised the filtered Operation Link, switching supervisors, mapped entry submission, independent stage balances and final completion. Ruff, ESLint and whitespace checks passed. Validation used only the isolated local production/dev test sites.

## Per-item ranges, recurrence, diagnostics and form layout (October 20, 2026)

Validated candidates based on production `f97185d` and dev `d242023` in the isolated local production/dev databases. No shared development or production site was changed.

- **60 production tests passed on each branch.** Coverage includes independent row ranges and mixed frequencies, header/custom-rule inheritance, row overrides outside default ranges, dated preview quantities, Once normalization, actual-date collision detection with row/item/date diagnostics, assignment limits, immutable submitted sources, browser-serialized date round trips, output-row errors and idempotent range migration. Historical submitted schedules with overlapping recurrence retain their source assignments and submitted production.
- **17 Stock Entry/variant regressions passed on each branch**, and **13 OEM domain/rules/boundary checks passed on dev**. Production's unrelated stock-inward changes and dev's OEM hooks remain on their respective branches.
- The original seven schedules, 12 assignments and 10 entries retained their source values and quantities after migration. Item From Date and To Date, frequency and custom rules are backfilled from the previous planning fields; assignments are not regenerated.
- Chromium passed the mixed Daily/Once/Weekly workflow on both candidates. A Daily row generated eight dates at 2,000 each (16,000 total); Once and Weekly rows generated one and three dates. Two responsibilities created 24 assignments, mapped to separate operation entries and progressed from 50% to Completed / 100%. The preview lists each generated date and quantity; an intentional overlap reported rows 1 and 4 and the actual conflicting dates.
- Browser checks cover header default changes preserving manual date/frequency overrides and an explicitly cleared weekday override. Desktop (1600px), expanded-row and mobile (390px) forms were inspected. Header defaults occupy aligned columns, the item grid is full width, custom recurrence/progress have separate sections, and redundant planning Schedule Date fields are hidden.
- Ruff, ESLint, JavaScript syntax and Git whitespace checks passed. The production test bench retains its previously documented barcode `installers` asset error; the scheduling workflow passed, including the intentionally triggered collision error.

Release installation requires the normal schema migration and restart of application processes to load the new controllers. This validation did not deploy or restart live services.
