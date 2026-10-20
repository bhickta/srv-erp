# Production scheduling

The Production Scheduling workspace provides recurring, multi-item production plans and linked production entries. Entries track actual quantities and completion; they do not post stock or consume raw materials.

## Setup

Assign **SRV Production Planner** to people who manage schedules and **SRV Production Supervisor** to responsible system users. System Managers also have planner access. An Item manager fills **Production Supervisor** on each Item template. Template defaults supply responsibility when the schedule has no explicit Responsibilities. To assign several people, add each user and their **Work Area / Operation** to the schedule (for example, Nishant — Fabrication and Anmol — Bending). **Work Area / Operation** links to the standard ERPNext **Operation** master. Create operations such as Fabrication and Bending there, then select them on responsibility rows. Each responsibility receives the full target for every scheduled item and date; entries and balances are independent.

The normal application migration installs the new child tables and converts existing single-item schedules and entries without renaming documents or changing their submitted quantities. Existing dated assignments retain their links and receive item-row references and completion percentages. Existing text work-area names are preserved by creating missing Operation records; the fallback Production operation is created automatically. The conversion can be run repeatedly without duplicating rows.

## Plan multiple templates or variants

1. Open **Production Scheduling → Production Schedules → New**. Enter a title, company and date range. **Schedule Date** defaults to the range start and supplies the date for new item rows.
2. In **Items to Produce**, add a row and select its **Template** first. The **Variant** picker shows only enabled variants belonging to that template. Leave Variant blank to plan production across that template, or select a variant to require that exact item.
3. Set **Qty / Date** and each row’s **Schedule Date**, then add more item rows. Item dates must lie inside the schedule range; recurrence starts at each item’s date and runs through End Date. Changing the header date updates rows still using its previous default and preserves manually chosen dates. Each row receives its template's supervisor and stock UOM. Different rows can have different default supervisors and UOMs. Explicit Responsibilities apply to every item instead of those defaults.
4. Choose Once, Daily, Weekdays, Weekly, Monthly or Custom, then use **Preview Dates**. The preview shows dates and each item's quantity per date and total planned quantity.
5. Save and submit. The system generates one dated assignment per item row, occurrence and responsibility. Open **View → Assignments Calendar** to see the dated plans.

**Plan Production** on a template or variant also starts a schedule with that item filled in.

Monthly recurrence retains the original day anchor, using month-end when necessary. Custom recurrence supports every N days/weeks/months, selected weekdays (`Mon,Tue,Wed,Thu,Fri,Sat,Sun`) or explicit dates, one per line. Weekly intervals count weeks from Monday; blank weekdays use the start weekday. Date boundaries are inclusive, and holidays are not automatically excluded. A schedule is limited to 1,000 dated item assignments and 3,660 days.

## Schedule → Production Entry

On a submitted schedule, choose **Create → Production Entry**. To map only specific item lines, select their table checkboxes first. Select a supervisor, their work area, and optionally one schedule date; leaving the date blank includes all their pending dates. The entry opens with the source item codes and names, schedule dates, pending quantities, UOMs and source references already filled in.

Adjust **Produced Qty** to the actual output. Remove rows that were not produced on this entry. For a specifically planned variant, the produced variant is fixed to that item. For a template-level plan, select an actual variant; rows can be duplicated to split the same dated target across several variants, as long as their combined quantity stays within the pending target.

Save a draft or submit. Drafts do not consume pending quantities. Submission updates each assignment, the schedule item rows and overall progress. **View → Production Entries** and the schedule's linked-document section show the related entries, like other ERPNext source-to-transaction flows. The next mapped entry brings in only remaining items and quantities.

Supervisors can open their own calendar assignments and use **Record Production** to create the same mapped entry for their supervisor and planned date. They do not need to re-enter plan references or item quantities. Future actual production dates, unrelated variants, mixed schedules and quantities exceeding a source target are rejected. One entry belongs to one schedule, supervisor and work area. The header Schedule Date is the earliest source date in that entry; each item retains its own exact assignment date. These dates are derived from the source, while **Production Date** records when the work actually occurred. Item names come from the selected Item master.

## Progress and statuses

| Schedule status | Meaning |
| --- | --- |
| Draft | Editable plan; no dated assignments have been generated |
| To Produce | Submitted plan with no submitted production yet |
| Partly Produced | Some production is submitted, with outstanding quantities |
| Completed | Every dated item target is fully produced |
| Cancelled | Schedule cancelled; further production is blocked |

Item rows show **Finished**, **Remaining** and **Work %**. Responsibilities show their own status and work completion. Work completion averages dated responsibility targets. Finished quantity requires every responsibility for that item/date to have completed the units; multiple responsibilities do not multiply physical planned quantities. For example, completing fabrication of 10 units while bending has produced zero gives 50% work completion, zero finished and 10 remaining. When bending finishes, the item reaches 10 finished and 100%. If a planner adjusts stage targets independently, the smallest target defines the physical quantity and every stage must still fulfill its own target to complete the plan. The header shows **Completion %**, total item lines and item lines remaining. Overall completion is the average fulfillment percentage of dated item assignments, which avoids adding incompatible UOMs. For example, one half-complete assignment and one complete assignment give 75%. Completion requires every assignment to reach its target, regardless of percentage rounding.

Production entries have Draft, Submitted and Cancelled statuses. Cancelling an entry reverses its contribution and can reopen a completed schedule. Only planners can cancel or amend entries. To cancel the schedule, reverse its submitted production first.

## Layout and access

Schedules and entries use compact column groups for their headers and full-width item tables. Submitted schedule source rows are read-only. Planners can adjust individual dated targets, dates or supervisors with a new change reason; changing Item defaults affects future plans only. Generated assignments and their schedules remain available for audit history.

Supervisors see only their own dated assignments. Every entry row must be accessible to its supervisor, and the server applies those checks to mapping, lists, direct document access and submission. Production records cannot be shared to bypass responsibility. Company user permissions continue to apply.

If assignments from a historical grouped entry are later split between supervisors, the complete entry becomes planner-only to prevent disclosing another supervisor's rows. Each assignment's quantities and progress remain correct. Parent schedules remain planner-only because they may include several supervisors' items.

## Verification

Run `srv_erp.tests.test_production_scheduling` on an isolated development test site. It covers recurrence, mapping, variant selection, multi-item progress, split output, cancellation, supervisor privacy, source immutability and legacy data migration.
