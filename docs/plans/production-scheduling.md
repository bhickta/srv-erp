# Production scheduling and supervisor entries

Status: proposed implementation plan; no application behavior changes in this PR.
Base: srv-erp `version-15` at `a1e114b`.

## Intended workflow

1. A manager sets an enabled responsible User / Production Supervisor on an Item template (`has_variants = 1`).
2. A production planner selects company, template(s), date range, frequency, and target quantity per occurrence. The form resolves the supervisor from each template and shows a dated preview before confirmation.
3. Confirmation creates separate dated production assignments. A calendar displays these assignments in month, week, and day views, with a list alternative.
4. A supervisor signs in, sees only assignments allocated to that user, opens one, and records production against it.
5. The assignment displays planned quantity, completed quantity, remaining quantity, and linked entries. Planners can monitor all assignments within their permitted companies.

## Proposed records

Use distinct names to avoid a collision with ERPNext's existing Production Plan.

| Record | Purpose and principal fields |
| --- | --- |
| Item custom field | `custom_production_supervisor`, Link to User, shown on templates; editable by authorized item managers. Validate an enabled system user with the supervisor role. |
| SRV Production Schedule | Company, inclusive start/end dates, frequency settings, selected templates, target quantity/UOM per occurrence, draft/confirmed/cancelled lifecycle. Holds recurrence rules and the confirmed preview. |
| SRV Production Schedule Item | Child rows containing template, target quantity, UOM, and resolved supervisor. Preview flags missing assignments and invalid quantities/conversions. |
| SRV Production Assignment | Standalone, permission-controlled occurrence: schedule, source row, template, supervisor snapshot, planned date, quantity/UOM, and status. Standalone records allow secure calendar queries and direct access. |
| SRV Production Entry | Submittable progress record linked to one assignment; actual date, variant output rows, quantities/UOM conversions, remarks, entered by, and optional stock transaction reference. |

Resolve responsibility from the template when confirming the schedule. Changing the Item default affects new schedules only. A planner may explicitly reassign unfinished assignments, with an audit trail; existing production retains its original attribution. Supervisors cannot reassign themselves or change targets/dates.

Plan at template level; enter actual output against concrete variants belonging to that template. Never post a template itself to stock. Sum output in the assignment's UOM using validated item conversions; reject incompatible conversions instead of adding quantities with different units. Store conversion snapshots for historical accuracy.

## Date range and frequency

- Standard: once, daily, weekdays, weekly, and monthly.
- Custom: every N days/weeks/months, selected weekdays for weekly recurrence, or explicitly selected dates within the range.
- Dates are company/site-local all-day dates with inclusive range boundaries. Once uses the start date.
- Monthly recurrence uses the original day anchor; when unavailable, use that month's last day. For example, January 31 produces February 28/29 and March 31.
- Show every generated date, target, total quantity, and supervisor before confirmation. Quantities are per occurrence; a range total is displayed separately.
- Reject reversed ranges, empty recurrence results, nonpositive intervals/targets, duplicate template rows, disabled templates/users, and missing supervisors. Cap generated occurrences with a clear validation message.
- Holidays are not automatically excluded in the first release. The preview permits deliberate date selection through the explicit-date frequency.
- Generation must be transactional and idempotent, backed by a unique key on schedule + source row + occurrence date. Retrying confirmation must not create duplicates.

## Calendar and plan lifecycle

Register a Frappe calendar for assignments. Display template, planned quantity/UOM, and progress, with color indicating planned, in progress, completed, or cancelled. Show overdue as a computed indicator for unfinished assignments before today.

Planners can filter by date, supervisor, template, company, and status. Supervisor filters cannot widen their accessible records. Selecting an event opens the assignment and offers Record Production.

Confirmed recurrence rules are immutable. Planners may reschedule/reassign individual unfinished occurrences with a reason; provide form controls first and defer drag-to-reschedule. Completed occurrences remain historical records. Cancelling a schedule cancels only occurrences without submitted production; require resolution of submitted entries before cancelling an affected occurrence. Do not delete history.

## Supervisor access

Introduce SRV Production Planner and SRV Production Supervisor roles. Planners manage schedules and assignments within allowed companies; supervisors read only their own assignments and enter production against those assignments. Administrator retains framework-level access.

Enforce supervisor ownership on the server through both permission query conditions and document permission checks. Apply it consistently to lists, direct URLs, calendars, link searches, reports, exports, entry reads, and every write endpoint. Do not rely on a client filter or document creator (`owner`).

A supervisor must not obtain another supervisor's schedule details through the shared parent schedule. Restrict schedule documents to planners; assignments expose only the necessary occurrence details. Check assignment access on entry creation, submission, cancellation, amendment, and reassignment. A supervisor with other standard roles must still satisfy these custom assignment restrictions unless explicitly granted planner access.

Restrict shared assignment/entry access, disable supervisor sharing, and ensure related dashboards, linked documents, and error messages do not disclose other assignments. Enforce company access as well as role and supervisor assignment. Test combined roles and explicit document shares.

## Production entry and progress

Allow multiple partial entries per assignment. Require positive quantities, a valid assigned template/variant relationship, enabled stock items where stock is posted, valid UOM conversions, and company-consistent warehouses where applicable.

Only submitted entries count toward completion. Draft entries have no effect. Cancellation reverses their contribution; amendments remain traceable. Calculate remaining quantity from submitted output, rather than trusting a client-supplied total. Serialize submission/cancellation against the assignment to prevent concurrent entries exceeding the target. Proposed default: block overproduction; planners must increase the target explicitly with a reason.

The meaning of production entry must be confirmed before implementation:

- Recommended first scope: SRV Production Entry records actual output and progress only; stock does not change. Label this behavior clearly in the entry form.
- If stock posting is required: agree whether this is Manufacture with BOM/Work Order and raw material consumption, or a finished-goods Material Receipt. Add warehouse, valuation, batch/serial, and package barcode requirements. Reuse ERPNext stock transactions and the existing SRV Stock Entry/package barcode validation. Never insert stock ledger entries directly.

For stock posting, count completion only when the linked stock transaction is submitted. Define one authoritative submission/cancellation flow, prevent duplicate stock transactions on retries, and validate assignment access on linked Stock Entries without widening general stock permissions. A supervisor's access to unrelated stock transactions must not be increased.

## Implementation sequence

1. Confirm the production-entry scope and the decisions below.
2. Add role setup and the template supervisor custom field through the app's installation/migration conventions; preserve existing Item hooks and variant behavior.
3. Add schedule and assignment DocTypes, recurrence generation, preview/confirmation, uniqueness constraints, and server permission rules.
4. Add the assignment calendar, planner controls, and supervisor My Production Assignments navigation.
5. Add production entries, partial completion, target checks, cancellation/amendment handling, and optional stock integration once its scope is agreed.
6. Add planner reporting for planned versus actual by date/template/supervisor, with UOM separation and the same permission rules.
7. Validate in an isolated development site under `~/development`; commit focused changes and open implementation PR(s). Deploy only through the normal reviewed process.

## Acceptance and verification

- Template supervisor selection is validated; creating variants does not require duplicate responsibility maintenance.
- Daily/weekly/monthly/custom previews and generated occurrences agree, including inclusive end dates, leap years, short months, and selected weekdays.
- Repeated/concurrent confirmation creates exactly one set of assignments; failed confirmation leaves no partial schedule.
- Supervisor A cannot list, open, query, export, share, or write Supervisor B's assignments or entries, including by forged IDs, calendar API calls, direct entry creation, and combined roles.
- A planner sees permitted-company assignments; company restrictions apply to calendar, reports, and entry endpoints.
- Partial entries accumulate correctly; drafts do not count; cancellations and amendments produce correct totals; concurrent submissions cannot bypass the target check.
- Reassignment preserves previous production history and applies the agreed visibility policy to the reassigned assignment.
- Variants from another template and invalid UOM conversions are rejected. Existing Item, stock valuation, and barcode behavior continue to work.
- If stock integration is selected, submission/cancellation, retries, permissions, and stock-to-plan totals are verified together.

## Decisions for the user

1. Should recording production update stock? If yes, is production BOM/Work Order based, or finished-goods receipt only?
2. Proposed quantity model: a target per occurrence at template level, with actual production broken down by variant. Is variant-level planning required instead?
3. Proposed permission model: supervisors record and submit entries for their own assignments; planners manage targets and dates. Does production submission need manager approval?
4. Proposed scheduling policy: calendar dates without holiday exclusion, overproduction blocked, and monthly missing dates moved to month-end. Are these suitable?
5. Proposed reassignment visibility: the new supervisor sees the assignment and its accumulated production; the former supervisor loses access to the reassigned assignment and its entries. Is historical access for former supervisors required?
