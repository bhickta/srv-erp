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
6. Validate detailed and grouped query paths against a site database when available.

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
- Run Python and JavaScript syntax checks, `git diff --check`, and relevant report tests or live read-only queries.
