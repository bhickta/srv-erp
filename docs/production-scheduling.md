# Production scheduling

The Production Scheduling workspace provides recurring, multi-item production plans and linked production entries. Entries track actual quantities and completion; they do not post stock or consume raw materials.

## Setup

Assign **SRV Production Planner** to people who manage schedules and **SRV Production Supervisor** to responsible system users. System Managers also have planner access. Item managers can fill **Production Supervisor** on templates as the fallback owner when a schedule has no explicit responsibilities.

To assign several people, add a user and **Work Area / Operation** to each schedule responsibility, for example Nishant — Fabrication and Anmol — Bending. Work Area / Operation links to ERPNext's **Operation** master. Each responsibility receives the full target for every generated item/date, with independent entries, pending quantities and completion.

## Plan items with their own date ranges

1. Open **Production Scheduling → Production Schedules → New**. Enter the title and company.
2. In **Planning Defaults**, set **Default From Date**, **Default To Date** and **Default Frequency**. They populate new item rows. Changing a default updates rows still using the previous value and preserves manual overrides. Each row may use its own date range, including dates outside the header defaults.
3. Add responsibilities, or leave the table empty to use each template's default supervisor.
4. In **Items & Date Ranges**, select **Template** first and optionally choose a specific **Variant**. Set the row's **From Date**, **To Date**, **Frequency** and **Qty / Date**. Leave Variant blank to plan output across that template; selecting a variant requires that exact produced item.
5. Use **Preview Dates** before submission. The summary shows each row's range, frequency, generated-date count, quantity per date and total planned quantity. Expand a row in the preview to see every generated Schedule Date and its quantity.
6. Save and submit. The system creates one assignment per generated item/date/responsibility. Open **View → Assignments Calendar** to see the plans.

Example: one item row with **23–30 October / Daily / 2,000 Qty per Date** produces eight dated targets and **16,000 total planned**. Do not add a separate row for every date of that same Daily range. To plan a single day, use **Once**; its To Date is normalized to From Date.

The same template or variant can appear on multiple rows if their generated production dates do not collide. Overlapping date ranges are allowed when their frequencies produce different dates. If two rows plan the same item on an actual generated date, validation identifies the item, both row numbers and the conflicting dates, for example **Date collision for item FB 374 in rows 1 and 3: 2026-10-27, 2026-10-28**. Change the range/frequency or combine the quantities. Existing submitted schedules with historical overlaps retain their original assignments during migration; new or edited plans use the collision check.

Expand an item row for **Custom Recurrence** and **Progress & Template Default** sections. Each row can override the header's custom interval, recurrence unit, weekdays and explicit dates. Monthly recurrence retains the original day anchor, using month-end when necessary. Custom supports every N days/weeks/months, selected weekdays (`Mon,Tue,Wed,Thu,Fri,Sat,Sun`) or explicit dates, one per line. Weekly intervals count weeks from Monday; blank weekdays use the row's From Date weekday. Date boundaries are inclusive; holidays are not automatically excluded. Each range is limited to 3,660 days and the whole schedule to 1,000 dated assignments including responsibilities.

**Plan Production** on a template or variant also starts a schedule with that item filled in.

## Schedule Date versus From/To Date

**From Date and To Date** are the item row's planning range. **Schedule Date** is the exact day on a generated assignment or production-entry item. The production-entry header shows the earliest source date in that entry, while each entry item retains its exact assignment date. **Production Date** is when the work actually occurred.

The earlier planning Schedule Date fields remain hidden for compatibility. Migration copies each historical item date into From Date and copies the old header recurrence into the row. Existing document names, assignments, source links and submitted quantities remain unchanged. Missing Operation records for historical work-area labels are created, including the default Production operation. Migration is repeatable and does not regenerate submitted assignments.

A matching Variant is retained when Template and Variant are filled together, including pasted or batch-edited rows. Changing Template clears a Variant that belongs to a different template. Item Name follows the current selection.

## Schedule → Production Entry

On a submitted schedule, choose **Create → Production Entry**. Select item checkboxes first to map only those rows. Choose a supervisor, their operation, and optionally a Schedule Date. Leaving the date blank includes all their pending dates. The entry opens with item codes and names, source dates, pending quantities and UOMs filled in.

If a saved schedule has no Variant, its mapped entry requires the actual produced variant in **Item Code**. The entry shows guidance and identifies each missing row, template and Schedule Date on Save. Select the correct variant directly in the entry to record production against an existing template-only plan. Missing historical selections are not inferred or backfilled.

Adjust **Produced Qty** and remove rows not produced on this entry. For a template-level target, select the actual variant. Duplicate an output row to split that target across variants; the combined quantity must stay within the source balance. One entry belongs to one schedule, supervisor and operation. Errors for invalid output or excess production include the output row, item, source date and pending quantity.

Save a draft or submit. Drafts do not consume pending quantities. Submission updates the assignments and schedule progress. The next mapped entry brings in the remaining quantities. Supervisors can also open their own assignment and use **Record Production**, which carries the operation and date automatically.

## Updating a submitted plan after production starts

Open a submitted **SRV Production Schedule** and click **Update Plan**. Planners can change each dated assignment's schedule date, supervisor and total target, including assignments with submitted production. Expand a dated row for its item name, UOM and status. Select several rows and use **Apply to Selected Rows** to set a common date, supervisor or total target. Enter a reason and click **Save Plan Updates**.

**Target** means the full required quantity, including the **Produced** quantity. **Remaining** previews the balance against the proposed target. For example, after producing 40 of 100, changing the target to 120 leaves 80 pending. The target cannot fall below submitted production. Raising a completed target reopens its pending work. When several operations should have the same physical target, select their rows together.

All changed rows save together. If another user changes an assignment or records production while the screen is open, reopen **Update Plan** to load the current balances. Errors identify the update row, item, operation, date and assignment; new collisions identify both assignments and the affected row(s). The collision check covers the same item, operation, supervisor and date in this schedule and permits atomic swaps of dates.

Submitted production entries retain their quantities, source dates and supervisor snapshots. Supervisors' access continues to follow the current assignment owner; after reassignment, mixed-owner entries remain planner-only. The schedule's original ranges, frequency, item identities and responsibility definitions remain the submission record. This action updates existing dated work; it does not regenerate recurrence, add items or remove production history. Use **View → Dated Plans** or **Assignments Calendar** for current dates and owners. Totals, pending quantities, percentages and statuses refresh after saving. Each assignment retains field change history and the reason, and the schedule timeline records the batch update and author.

This change adds no database fields. Deploy the app code, clear the site cache and restart app processes through the normal deployment process.

## Progress, layout and access

Schedules move through **Draft → To Produce → Partly Produced → Completed**, or **Cancelled**. Entry statuses are Draft, Submitted and Cancelled. Responsibilities have Planned, In Progress, Completed and Cancelled statuses.

The header shows work completion and item lines remaining. Each row's expanded progress section shows finished/remaining quantities and Work %. Overall work completion averages dated responsibility targets. Multiple responsibilities do not multiply physical planned quantities: finishing fabrication of 10 units while bending has produced zero gives 50% work completion, zero finished and 10 remaining. When bending finishes, the item reaches 10 finished and 100%. If planners change stage targets independently, the smallest target defines physical quantity; every stage must fulfill its own target before the plan completes.

Cancelling an entry reverses its contribution and can reopen the plan. Only planners can cancel or amend entries. Reverse submitted production before cancelling the schedule. Submitted source ranges, recurrence and responsibilities are immutable; planners can adjust dated assignments with a new change reason.

The form groups Planning Defaults, Responsibilities and Items & Date Ranges separately. The item grid shows the planning fields and total quantity; expanded rows group item identity, dates/quantity, custom recurrence and progress into sections and columns. Legacy planning dates are hidden.

Schedule, Assignment and Entry lists hide configured Cancelled, Rejected and Disabled statuses by default for all users. Users may remove/change the filter to inspect history. Explicit saved status/document-status filters are respected; existing views without one receive the default on opening. Document permissions are unchanged.

Supervisors see their own dated assignments and entries. Mapping, lists, direct reads, child-table access and submission apply ownership and company permissions. Production records cannot be shared to bypass responsibility. If a historical grouped entry is later split between supervisors by reassignment, it becomes planner-only to protect other users' rows. Parent schedules remain planner-only because they can contain multiple users' plans.

## Verification

Run `srv_erp.tests.test_production_scheduling` on an isolated development test site. It covers recurrence, per-row ranges, defaults, preview quantities, date collisions and diagnostic messages, item/variant mapping, independent operation balances, source immutability, supervisor privacy, cancellation and repeatable migration.
