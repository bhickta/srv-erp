# Quality report print layouts

## Frappe integration

- Name the template exactly like the report: `report_name/report_name.html`.
- Frappe exposes `report`, `filters`, `data`, `columns`, `subtitle`, and `print_settings` to the microtemplate.
- Use `{%= ... %}` for escaped output, `{{ ... }}` only for intentionally generated HTML, and `{% ... %}` for control flow.
- For a view-specific template, add:

```javascript
get_pdf_format(report, custom_format) {
	return report.get_filter_value("special_view") ? custom_format : null;
}
```

This preserves the generic `print_grid` path for other views. User-selected print formats or explicit print columns continue to take precedence in Frappe.

## A4 baseline

Use portrait for up to roughly six compact columns; use landscape only when the content requires it.

```css
@page { size: A4 portrait; margin: 12mm; }
thead { display: table-header-group; }
tr { page-break-inside: avoid; }
table { width: 100%; table-layout: fixed; border-collapse: collapse; }
.number { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
```

Use restrained grayscale styling so print remains legible without color. Repeat headers across pages, prevent row splitting, and keep font sizes at least 8.5–10pt for data.

## Recommended structure

1. Centered report title and view name.
2. Compact metadata block for company, warehouse, and date range.
3. Fixed-width table with left-aligned identifiers and right-aligned quantities.
4. Bold group headers, indented details, ruled totals, and short blank separators.
5. Muted printed timestamp.

Do not repeat metadata as table columns. Do not rely on screen-only CSS classes or DataTable markup in the print template.

## Quantity rendering

Keep values numeric in Python. Render a quantity and its UOM together:

```javascript
const quantity = (value, uom) => {
	if (is_null(value)) return "";
	const formatted = frappe.format(value, { fieldtype: "Float" });
	return `${formatted}${uom ? ` <span class="qty-uom">${frappe.utils.escape_html(uom)}</span>` : ""}`;
};
```

Ensure totals retain the same UOM field as detail rows. Split totals when a group contains multiple UOMs.

## Validation checklist

- Print and PDF use the custom template only for the intended view.
- Generic printing still works for legacy views.
- A4 pagination repeats headers and does not split rows.
- Empty, one-group, multi-group, mixed-UOM, and multi-page datasets render correctly.
- Displayed totals match raw numeric fields.
- Long item codes and brand names wrap without covering quantity columns.
