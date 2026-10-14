# Ticket PP-003 — Production planning from trailing sales with ratio targets (brand-less)

**Type:** Implementation handoff for a coding agent
**App:** `srv_erp` (custom Frappe/ERPNext app, repo `github.com/bhickta/srv-erp`)
**Baseline:** `origin/version-15` @ `1898613`
**Status:** Specification only. No application code was changed, no migration was run, and no tests
were executed while preparing this document.

---

## 1. Summary

Add a production-planning report that uses the **trailing three months of sales**, aggregates them
**item-wise and brand-less**, and derives planning quantities by applying a **percentage ratio** to the
quarter's sales. It also renders a **chart of the sales**.

Requester's own words (2026-10-14):

> "हमें फीचर production planning निकालनी है … तीन महीने की sales को लेकर उसका quarter देखा जाए, quarterly
> हमने कितना sale किया है … item-wise मेरी planning कितनी हो, without brand वाली … जो quarter में जितनी
> sale हुई है उसके according one-to-one मैं planning दे दूंगा … multiple ratio में दे देंगे … 30% 40% …
> chart दे देंगे और दूसरा ratio में देंगे 70% और 100%"

Translation: *we want production planning; take three months of sales, look at it quarterly (how much we
sold); item-wise planning without brand; the planning is 1:1 with the quarter's sales by default, and we
can also give multiple ratios (30 %, 40 %, 70 %, 100 %); and show a sales chart.*

---

## 2. Source evidence

Audio: `WhatsApp Audio 2026-10-14 at 6.21.22 AM.mp4` (867.8 s); timestamps from the high-accuracy
transcript (Appendix A).

| Time | Statement (cleaned) | Requirement extracted |
|---|---|---|
| 10:51–11:08 | "हमें फीचर production planning निकालनी है … तीन महीने की sales को लेकर उसका quarter देखा जाए, quarterly हमने कितना sale किया है और वह सेल हमारी future production planning में आड़ होंगे" | Use ~3 months of sales, viewed quarterly, feeding future production planning. |
| 11:14–11:31 | "item-wise मेरी planning कितनी हो, ब्लन्ड/ब्रांड वाली नहीं … मेरा customer और item code … जो quarter में जितनी sale हुई है उसके according one-to-one मैं planning दे दूंगा" | Item-wise (not brand-split); 1:1 planning from quarterly sales by default. |
| 11:54–12:11 | "अगर कुछ और ratio चाहिए … multiple ratio में दे देंगे … एक customer, srv xyz item code के लिए quarter में 300 तो … 3-4 row दे सकते हैं percentage wise यह 30% 40%" | Configurable ratios; example quarterly qty 300 with 30 % / 40 % rows. |
| 12:20–12:45 | "उनकी sale का chart बन जाए … चार्ट दे देंगे और दूसरा ratio में देंगे 70% और 100% … 300 का 100% = 300, 70% = …" | A sales chart plus 70 % / 100 % ratio scenarios. |
| 12:45–12:54 | "तीन महीने की sale निकालेगा और उसमें देख लेंगे कितने percent उसको sale में से बनाना है" | Take 3 months of sales and choose what percentage to produce. |

---

## 3. Baseline and existing building blocks (read before coding)

| File | Relevance |
|---|---|
| `srv_erp/srv_erp/report/items_ordered_in_date_range/items_ordered_in_date_range.py` | Closest existing report: computes `stock_ordered_qty`, `stock_delivered_qty`, `stock_available_qty`, `stock_pending_qty`, `stock_shortfall_qty` ("Qty to Manufacture"); resolves brand via `RESOLVED_BRAND_SQL`; supports `SO UOM` vs `Stock UOM` display (`convert_data_to_display_uom`, `get_display_uom_and_factor`), a grouped view, and a subtotal view. **Study first.** |
| `srv_erp/srv_erp/report/items_delivered_in_date_range/items_delivered_in_date_range.py` | Delivered-quantity SQL pattern. |
| `srv_erp/srv_erp/report/hierarchical_filters.py` → `get_descendant_condition()` | Descendant-inclusive tree filtering for the Item Group filter. Reuse. |
| `srv_erp/srv_erp/report/uom_utils.py` | Existing `UOM Conversion Detail` factor loading and `add_additional_uom_columns()`. Reuse. |
| Existing report folders | `<name>.py` + `<name>.json` + `<name>.js`, registered like the other reports. |

There is **no** planning/ratio report today. The current reports are `items_ordered_in_date_range`,
`items_delivered_in_date_range`, `variant_coverage`, `stock_balance`, `maximum_stock_exceeded`,
`stock_inward_register`, and the `dsr_*` reports.

---

## 4. Required behaviour

1. **New report** `production_planning` under `srv_erp/srv_erp/report/production_planning/`
   (`.py`, `.json`, `.js`).
2. **Trailing window.** A look-back filter in months, default **3**, interpreted as whole quarters; also
   allow explicit `from_date`/`to_date` overrides.
3. **Item-wise, brand-less.** Aggregate sold quantity by item **without** splitting by brand. Document
   whether variants roll up to their template (see §6 Q1).
4. **Quarterly sales columns.** Show the sales quantity per quarter in the window, in stock UOM by
   default, with the existing `SO UOM` / `Stock UOM` display option.
5. **1:1 default.** The default planning figure equals the quarter's sales (100 %), matching the
   requester's "one-to-one" statement.
6. **Ratio scenarios.** Support the ratio set **30 %, 40 %, 70 %, 100 %** (confirm exact set and store in
   `SRV Settings` rather than hard-coding — §6 Q3). Either show one column per ratio or let the user pick
   a single ratio; both were described.
7. **Correct rounding.** `planning_qty = sales_qty × ratio / 100`, rounded to the item's UOM precision,
   not a fixed 2 dp.
8. **Chart.** Return a Frappe `chart` of the quarterly sales totals.
9. **Filters.** Company and Warehouse required (reuse `set_default_warehouse` / `validate_warehouse`),
   plus optional Item Group (hierarchical), Item, Brand, and the ratio selection.
10. **Sales basis.** Base "sold" on submitted Sales Orders (consistent with existing reports), excluding
    `Closed`/`Completed`; state the choice. (See §6 Q2.)
11. **Performance.** Single aggregated SQL + in-Python grouping, following the existing reports; no
    per-item queries.

---

## 5. Affected files (expected)

- `srv_erp/srv_erp/report/production_planning/__init__.py` — new.
- `srv_erp/srv_erp/report/production_planning/production_planning.py` — new.
- `srv_erp/srv_erp/report/production_planning/production_planning.json` — new.
- `srv_erp/srv_erp/report/production_planning/production_planning.js` — new.
- Workspace/desk registration where other reports are surfaced.
- `srv_erp/tests/` — new test module.

---

## 6. Open questions

**Q1 — Variant vs template aggregation.** The app is variant-heavy (one template, many brand/attribute
variants). Should the report roll variants up to the template, or list each variant item separately?
**Recommendation:** roll up to template by default, with a "Show variants" switch.

**Q2 — Sales Order vs Delivery Note basis.** Which document defines "sold" for planning?
**Recommendation:** submitted Sales Orders, matching the existing reports.

**Q3 — Ratio source and set.** Confirm the exact default ratios (30/40/70/100 read from the note) and
whether they live in `SRV Settings`.

**Q4 — Quarter definition.** Calendar quarters vs rolling 90-day buckets. **Recommendation:** calendar
quarters aligned to the trailing window.

**Q5 — Stock offset.** The existing "Qty to Manufacture" is `Ordered − Delivered − Stock`. Should the
planning quantity also subtract available stock, or stay a pure ratio of sales as the requester
described? **Recommendation:** show both — the pure ratio figure and an optional stock-adjusted figure.

**Q6 — Customer dimension.** The note mentions "मेरा customer और item code". Should the report support a
Customer filter/grouping in addition to item-wise aggregation?

---

## 7. Ordered implementation checklist

1. [ ] Read `items_ordered_in_date_range.py` and `items_delivered_in_date_range.py` fully.
2. [ ] Confirm Q1–Q6 with the requester; record answers in the PR.
3. [ ] Create the report folder with `.json`/`.js` (filters + chart wiring).
4. [ ] Implement the aggregated brand-less sales query for the trailing window.
5. [ ] Implement the ratio columns with correct UOM precision.
6. [ ] Implement the chart return value.
7. [ ] Add tests.
8. [ ] Lint/format and `bench build --app srv_erp`.
9. [ ] Open the PR with the filter list, sample output, chart description, and test evidence.

---

## 8. Test matrix

| Area | Required cases |
|---|---|
| Windowing | Default 3 months; explicit from/to; quarter bucketing across a year boundary |
| Aggregation | Multiple Sales Orders for one item sum; brands are **not** split; closed/completed orders excluded |
| Ratio | 30/40/70/100 % give `sales × ratio / 100`; the 100 % scenario matches raw sales |
| UOM | Stock UOM default; `SO UOM` display converts correctly; UOM precision respected |
| Filters | Item Group descendants included; required company/warehouse validation; missing Finished Goods warehouse raises the existing error |
| Chart | One value per quarter with the expected totals |
| Performance | Query count does not scale with item count |

---

## 9. Definition of done

- A working `production_planning` report with the §4.9 filters.
- Correct item-wise, brand-less quarterly sales and ratio-based planning quantities (1:1 default).
- A quarterly-sales chart.
- Tests pass; the PR states the chosen basis (Q2), aggregation (Q1), and ratio source (Q3).
- No duplication of the existing hierarchical-filter or UOM helpers.

---

## Appendix A — Clean transcript excerpt (source of truth)

Audio: `WhatsApp Audio 2026-10-14 at 6.21.22 AM.mp4`, 867.8 s. Relevant segments (high-accuracy `large-v3`):

```
[00:10:51] ... अच्छा लिए इस पर क्या है ना कि हमें फीचर production planning निकालनी है
[00:11:01] तो सर का आइडिया यह इसलिए जो है तीन महीने की sales को लेकर उसका कॉर्टर देखा जाए
[00:11:08] कॉर्टरली हमने कितना sale किया है और वह जो है सेल हमारी फ्रूचर production planning में आड़ होंगे
[00:11:24] ... कि item-wise मेरी planning कितनी हो, ब्लन्ड वाली ने
[00:11:39] ... मेरा customer और आइटम कोड ... जो क्वार्टर में जितनी sale हुई है उसके according one-to-one मैं planning
[00:11:54] दे दूंगा अगर कुछ और ratio चाहिए ... multiple ratio में दे देंगे ... 
[00:12:01] ... एक कस्टमर srv xyz item code के लिए quarter में 300 तो ... 3-4 row दे सकते हैं, percentage wise यह 30% 40% ...
[00:12:20] ... सेल का जो हमारे पास डाटा चार्ट में आ जाए ... chart बन जाए ...
[00:12:37] ... चार्ट दे देंगे और दूसरा ratio में दे देंगे 70% और 100% ...
[00:12:45] ... तीन महीने की sale निकालेगा और उसमें देख लेंगे कितने परसेंट उसको sale में से बनाना है
```

Full transcript and `.srt` retained by the requester.
