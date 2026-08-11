---
name: frappe-report-making
description: Create and update Frappe or ERPNext Script Reports and Query Reports with safe default filters, correct transaction status handling, and hierarchical group filtering. Use for report Python, JavaScript, JSON metadata, SQL/query-builder logic, report columns, filters, grouping, totals, permissions, and report tests.
---

# Frappe Report Making

Build reports that are safe by default, auditable, and consistent with Frappe data semantics.

## Workflow

1. Inspect the reference DocTypes and nearby reports before choosing fields or joins.
2. Confirm whether each source DocType is submittable, has a `disabled` field, or is a nested-set tree.
3. Define filters and defaults before writing the data query.
4. Parameterize every user value. Never interpolate user-controlled values into SQL.
5. Keep quantities in compatible UOMs when aggregating. Group by UOM or convert to stock UOM first.
6. Add an optional `include_uom` Link filter to every report that lists Item quantities, following Stock Balance behavior.
7. Validate detailed and grouped query paths against a site database when available.

## Data correctness

### Resolve fields from their source of truth

- Verify where a displayed dimension is actually maintained; do not trust a copied transaction-child field merely because it exists.
- Resolve inherited or variant data from the authoritative master. For example, a variant Brand may live in `Item Variant Attribute`, then fall back to the Item or template Brand.
- Use the exact same resolved expression for the column, filter, grouping, and ordering so they cannot disagree.

### Define the aggregation grain

- State what one result row represents before writing `GROUP BY`.
- When grouping by Item, group by Item and UOM if the same Item can be ordered in multiple UOMs. Otherwise convert every quantity to Stock UOM and show that UOM.
- Never sum quantities expressed in different UOMs.
- Preserve the transaction and Stock UOM quantities. When `include_uom` is selected, add adjacent converted quantity columns using the Item's `UOM Conversion Detail`; use ERPNext's `add_additional_uom_columns` helper where possible.
- Mark only Stock UOM quantity fields as `convertible: "qty"`. Do not convert transaction-UOM totals as though they were Stock UOM totals.
- Treat Include UOM like Stock Balance: it adds converted quantity columns and never changes the Item's actual Stock UOM. Keep the selected UOM visible in each converted column label.
- Put every related UOM column immediately to the right of its quantity column. Name the pair `<quantity>` and `uom_<quantity>`: for example, `qty, uom_qty`, `stock_qty, uom_stock_qty`, and `delivered_qty, uom_delivered_qty`. Apply the same pattern consistently to all other quantity fields.
- Name each UOM label after its quantity label rather than using an ambiguous `UOM` or `Stock UOM`: for example, `Qty Ordered, Qty Ordered UOM` and `Stock Qty Delivered, Stock Qty Delivered UOM`.
- Keep each quantity and UOM semantically synchronized. Transaction quantities use the transaction UOM; stock quantities use Stock UOM; pending, delivered, deficit, returned, and other derived quantities must use the UOM of the source quantities used in their calculation.
- When showing the same quantity in an alternate UOM, convert from its Stock UOM quantity with the Item conversion factor and emit another complete adjacent pair, such as `stock_pending_qty_alt, uom_stock_pending_qty_alt`. Never relabel a quantity without converting its value.
- Calculate a grouped rate as `SUM(amount) / NULLIF(SUM(qty), 0)` at a compatible grain; do not use a simple average of line rates.
- Decide whether pending quantity is the sum of line-level pending quantities or the difference of aggregate ordered and delivered quantities, then test over-delivery and return cases.

### Keep grouped and detailed modes coherent

- When a report supports grouped and detailed modes, generate columns appropriate to each mode.
- Omit order-level dimensions such as document number, date, or customer from grouped output unless they are part of the grouping grain.
- Apply the same permission, status, date, and dimension filters to both query paths.
- Use deterministic ordering with stable tie-breakers. When sorting by a resolved field, use the same unambiguous expression rather than a conflicting alias.
- Wrap long query-report header labels and increase the header-row height so full column names remain readable. Prefer a shared app-level style scoped to `.report-wrapper` for consistent behavior across reports.

### Protect row cardinality

- Review every one-to-many join for row multiplication before aggregating.
- Use `EXISTS` for filters such as Sales Person when the joined rows are not report rows.
- Use a correlated aggregate or pre-aggregated subquery for comma-separated labels instead of directly joining a child table.
- Compare source row counts and totals before and after adding joins.

### Make date semantics explicit

- Choose the business date belonging to the report subject: transaction date for orders, posting date for submitted stock/accounting transactions, or delivery date only when the report explicitly concerns scheduled delivery.
- Label filters and date columns accordingly; do not silently mix order-date and fulfillment-date ranges.

### Keep warehouse availability distinct from transaction quantities

- Do not label a transaction line's `stock_qty` as stock available. It is the transaction quantity converted into Stock UOM, not warehouse inventory.
- For current on-hand stock in one warehouse, read `Bin.actual_qty` by Item and Warehouse and display the Item's `stock_uom` beside it. State explicitly that this is current stock, not stock as of the report's transaction date.
- If “available” means stock remaining after reservations, define the business formula explicitly; `Bin.actual_qty`, projected quantity, and actual quantity minus reservations are different measures.
- Add a Warehouse Link filter whenever availability is warehouse-specific. Restrict it to enabled, non-group Warehouses belonging to the selected Company, and repeat that validation on the server.
- Remember that Frappe's Warehouse document `name` normally includes the company abbreviation, while `warehouse_name` does not. For example, look up `warehouse_name = "Finished Goods"` for the Company to resolve a document name such as `Finished Goods - SE`; do not hardcode the abbreviation-bearing document name.
- A `Bin` join must not multiply grouped availability by the number of order or invoice rows. At an Item/Warehouse grain use the one Bin value (for example `MAX(COALESCE(bin.actual_qty, 0))` after a safe join), rather than `SUM(bin.actual_qty)`.

## Mandatory defaults

### Disabled records

- Exclude disabled records by default whenever the source DocType defines `disabled`.
- Add an `include_disabled` Check filter with default `0` when users may need disabled records.
- Apply the disabled condition only when `include_disabled` is false.
- Verify DocType metadata first; never assume every DocType has `disabled`.
- Apply the rule to joined masters too when disabled linked records should not appear.

```javascript
{
	fieldname: "include_disabled",
	label: __("Include Disabled"),
	fieldtype: "Check",
	default: 0,
}
```

### Document status

- For submittable transaction DocTypes, include only `docstatus = 1` by default.
- Never include Draft (`docstatus = 0`) or Cancelled (`docstatus = 2`) records in default results.
- If alternate states are a genuine requirement, add a Document Status filter whose default is `Submitted`; make `Draft`, `Cancelled`, or `All` explicit user choices.
- Apply status conditions to the parent transaction, not merely its child table.

### Warehouse defaults

- When a report is intended to show finished-goods availability, default the Warehouse by resolving the enabled, non-group `Warehouse` whose `warehouse_name` is `Finished Goods` and whose `company` matches the selected Company.
- Keep the Warehouse filter visible and required so users know which inventory location the quantity represents and can select another location.
- Refresh or re-resolve the default Warehouse when Company changes, and validate the submitted filter server-side instead of trusting the client default.
- If the expected Finished Goods Warehouse does not exist, require an explicit Warehouse selection or show a clear error. Never silently fall back to an unrelated warehouse.

### Hierarchical groups

- Treat tree filters as subtree filters. Selecting a parent must include the selected group and every descendant at any depth.
- Apply this to `Item Group`, `Customer Group`, and any other verified NestedSet group DocType.
- Do not use exact equality for a tree filter unless the user explicitly requests exact-only matching.
- Use fixed, trusted table and column names. Continue parameterizing the selected group value.

```sql
transaction.item_group IN (
	SELECT child.name
	FROM `tabItem Group` selected
	INNER JOIN `tabItem Group` child
		ON child.lft >= selected.lft AND child.rgt <= selected.rgt
	WHERE selected.name = %(item_group)s
)
```

Use the equivalent `Customer Group` subtree for customer-group filters. A leaf selection naturally matches only itself.

## Verification checklist

- Verify default output contains no disabled records when applicable.
- Verify default transaction output contains only submitted documents.
- Verify opting into disabled or alternate statuses changes results intentionally.
- Test a leaf group, an intermediate parent, and the root group.
- Confirm parent-group totals equal the selected group plus all descendants without duplicate rows.
- Test repeated child rows do not multiply quantities or amounts.
- Test one Item used with multiple UOMs and verify grouped totals and weighted rates.
- Verify every quantity column is immediately followed by its `uom_<quantity>` column in both the definition and rendered output.
- Reconcile ordered, delivered, pending/deficit, and alternate-UOM quantities through the conversion factor; verify `alternate quantity × conversion factor = stock quantity` for representative rows.
- Select an Include UOM and verify its columns and conversion factors match Stock Balance for the same Items.
- Verify derived dimensions return the same records when displayed, filtered, grouped, and sorted.
- Verify warehouse availability matches `Bin.actual_qty` for the selected Item/Warehouse, remains unchanged when the same Item appears on additional transaction rows, and uses the Item's Stock UOM.
- Verify the default `Finished Goods` warehouse resolves to the Company-suffixed Warehouse document name and changes correctly when Company changes.
- Run Python and JavaScript syntax checks, `git diff --check`, and relevant report tests or live read-only queries.
