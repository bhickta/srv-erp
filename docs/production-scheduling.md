# Production scheduling

Production Scheduling adds recurring, template-level plans and supervisor production tracking. Production entries record quantities and progress; they do not post stock or consume raw materials.

## Setup

The standard application install/migration creates the **SRV Production Planner** and **SRV Production Supervisor** roles, the Item **Production Supervisor** field, and the Production Scheduling workspace.

Assign the supervisor role to responsible system users. An Item manager selects an enabled supervisor on each Item template. Item editing continues to require existing Item write permissions. Assign the planner role to users who manage schedules. System Managers also have planner access.

The new roles receive read access to Item, UOM and Company, and selection access to User. They receive no Stock Entry rights. Existing Company user permissions also restrict production records.

## Plan production

1. Open **Production Scheduling → Production Schedules**, or use **Plan Production** on an Item template.
2. Select a company and enabled template, target quantity per occurrence, and an inclusive date range. The template supplies the supervisor and stock UOM.
3. Select Once, Daily, Weekdays, Weekly, Monthly, or Custom. Custom supports every N days/weeks/months, selected weekdays for weekly intervals, or explicit dates entered one per line. Weekdays use `Mon,Tue,Wed,Thu,Fri,Sat,Sun`; blank weekly selection uses the start weekday.
4. Use **Preview Dates** to review the supervisor, dates, occurrence count, and total quantity. Save and submit to generate dated assignments atomically.
5. Open **Assignments Calendar** or the workspace's **Production Calendar** shortcut. Calendar titles show completed/target quantity. Open an assignment to record production or review its entries.

Each schedule covers one template. Monthly rules keep the original day anchor and use month-end when necessary: January 31 → February 28/29 → March 31. Custom weekly intervals count calendar weeks starting Monday. Holidays are not automatically excluded. Schedules are limited to 1,000 occurrences over at most 3,660 days. Overlapping independent schedules are permitted; retrying submission does not duplicate a schedule's occurrences.

## Record production

Supervisors can see only assignments allocated to them and entries linked to those assignments. They cannot open the planner's parent schedules. These restrictions apply to lists, calendar feeds, entry APIs and direct document access. Production records cannot be shared because Frappe v15 sharing can bypass custom permission checks.

Open an assignment and click **Record Production**. Select an enabled concrete variant of its template and enter the output quantity, actual date and optional remarks. Quantities use the variant's stock UOM, which must match the planned UOM. Future production dates and nonpositive quantities are rejected.

Save a draft or submit the entry. Only submitted entries count toward completion. Multiple entries support partial production and different variants. Completed quantity and remaining quantity appear on the assignment, and its status moves from Planned to In Progress to Completed. Submitted production cannot exceed the target. Conflicting simultaneous submissions are serialized; MariaDB snapshot conflicts use Frappe's standard reload/retry message.

## Planner corrections

Planners can change an assignment's date, supervisor or target with a new change reason. They cannot change its source schedule, company, template or UOM. The target cannot fall below submitted production. Changing the Item's default supervisor affects future schedule confirmations; it does not reassign existing occurrences.

Reassignment transfers visibility of the assignment and its historical entries to the new supervisor. The old supervisor loses access. Entry attribution and document versions remain in the audit history.

Only planners can cancel production entries; cancellation reverses progress. Planners can amend cancelled entries. To cancel a schedule, cancel its submitted entries first. Cancelling the schedule marks its assignments Cancelled and prevents further entries, including submission of existing drafts. Generated assignments and their schedules are retained for history.

## Verification

The automated module is `srv_erp.tests.test_production_scheduling`. It exercises recurrence boundaries, generation retries, supervisor/list/calendar access, share prevention, standalone planner permissions, partial completion, overproduction, cancellation and reassignment. Run it on an isolated Frappe/ERPNext development test site:

```sh
bench --site <test-site> run-tests --module srv_erp.tests.test_production_scheduling --skip-test-records --skip-before-tests
```
