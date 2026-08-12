---
name: frappe-report-builder
description: Build or improve polished Frappe and ERPNext Script Reports and Query Reports, including filters, grouped/subtotal views, planning-focused columns, hierarchy formatting, tests, and report-specific A4 HTML/PDF print layouts. Use for report Python, JavaScript, JSON, or same-named HTML print templates, and when an existing report view must remain backward compatible.
---

# Frappe Report Builder

Create reports whose data semantics, screen presentation, exports, and print output agree. Prefer established Frappe/ERPNext report conventions over one-off UI code.

## Workflow

1. Locate the report's `.py`, `.js`, `.json`, tests, and same-named `.html` template. Inspect comparable core ERPNext reports before editing.
2. Record existing filter defaults, columns, data order, saved-filter compatibility, and print behavior. Treat them as a compatibility contract unless the user explicitly replaces them.
3. Define each metric before writing SQL: grouping key, unit, aggregation, source field, and whether joins can duplicate it.
4. Implement server data and columns together. Keep alternate views behind an explicit filter and leave the old default path intact.
5. Add hierarchy metadata such as `indent`, `is_group`, and `is_total`; append `{}` between groups when a readable visual break is useful.
6. Add a same-named report HTML template for bespoke printing. If it applies only to one view, return it conditionally from `get_pdf_format(report, custom_format)` and return `null` for legacy views.
7. Add focused tests for grouping boundaries, every numeric subtotal, mixed UOMs, blank separators, and legacy columns/defaults.
8. Validate Python syntax, `git diff --check`, report tests, and—when available—HTML/PDF rendering on representative multi-page data.

## Data rules

- Aggregate quantities in a common UOM. Prefer stock quantities with `stock_uom` when Ordered, Stock, Delivered, and Remaining must be compared.
- Never add values carrying different UOMs. Emit separate total rows per UOM when conversion is unavailable.
- Prevent inventory multiplication when order rows join bins. Aggregate orders and inventory independently, then join their grouped results.
- Resolve item variants deliberately. For template-level planning, group with `COALESCE(NULLIF(item.variant_of, ''), item.name)` and resolve the business attribute from variant, item, then template.
- Keep numeric values numeric in returned data. Attach UOM labels in the screen formatter and print template, not by converting values to strings in Python.
- Define Remaining explicitly. For Sales Orders, normally use `GREATEST(stock_qty - delivered_qty, 0)` in the stock UOM.

## Presentation rules

- Show only decision-useful columns for planning views. Put context such as company, warehouse, and dates in print metadata instead of repeating it in every row.
- Use a clear hierarchy: group header, indented detail rows, strong total rule, then whitespace.
- Format quantities consistently with tabular numerals and muted UOM labels.
- Use semantic row flags rather than row-position assumptions.
- Escape UOMs and other injected text in client templates.

Read [references/quality-print.md](references/quality-print.md) whenever creating or changing a report-specific print/PDF layout.
