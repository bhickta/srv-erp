# Ticket DN-002 — Scanned Delivery Note rows must carry a Sales Order reference and the correct UOM

**App:** `srv_erp` (custom Frappe/ERPNext app, repo `github.com/bhickta/srv-erp`)
**Baseline:** `origin/version-15` @ `1898613` (Merge PR #85 `feat/delivery-note-barcode-scanning`)
**Related:** Ticket `DN-001` (Delivery Note UOM conversion, quantity entry, and multi-row Sales Order
accounting). DN-001 owns the conversion/quantity contract; this ticket owns the **scan → row** mapping.
Land DN-001 first or together.
**Status:** Specification only. No application code was changed, no migration was run, and no tests
were executed while preparing this document.

---

## 1. Summary

The requester names the multiple-row defect explicitly:

> "मल्टिपल row का इशु बस है कि जो स्कैन करने पर एक न्यू row ऐड हो रही है, उसका Sales Order पर कोई
> reference नहीं है … उसका जो Sales Order reference हो ताकि वो item से मैच कर जाए।"

Translation: *the problem with multiple rows is that scanning adds a new row that has **no Sales Order
reference**, so it does not match the ordered item.* The scanned row must reference the Sales Order line
it belongs to, use the package barcode's UOM, and merge into the existing row when the UOM converts.

---

## 2. Source evidence

Audio: `WhatsApp Audio 2026-10-14 at 6.21.22 AM.mp4` (867.8 s); timestamps from the high-accuracy
transcript (Appendix A).

| Time | Statement (cleaned) | Requirement extracted |
|---|---|---|
| 03:40–04:22 | "जो item स्कैन कर रहा है, उसके बारकोड में पैकेज UOM में जो है वही यूज़ बनाते हुए … अगर यह different हो रहा है तो … box में था और package बारकोड में box में था तो जो original pieces में order था वो row को रखेगा, और box वाली जो barcode scan हुआ है उसकी row अलग नहीं बना देगा" | Use the package barcode's UOM; do not create a duplicate/separate row when a matching original row exists. |
| 04:22–04:29 | "जो पहले row already है उसका जो UOM है, अगर वो UOM convertible है तो वो उसमें ही add करते" | If the existing row's UOM is convertible, **add into that row**. |
| 04:48–05:15 | "जो UOM पैकेज बारकोड में उसी UOM … आपने एक बैच … बॉक्स बना तो बॉक्स आ गया, आपने एक बैच और … नंबर का आइटम कोड सेम है, वह स्कैन करते उसमें एक और row add कर दी" | Use the barcode's UOM; a later scan that is not convertible legitimately adds another row. |
| 05:30–05:40 | "मेरा Sales Order में बॉक्स में है और मैं जब आ रहा हूं DN में मैंने पहले स्कैन नंबर वाला और मैंने बॉक्स वाला … तो मुझे कैसे पता देगा कि कौन सा वह चाह रहे हैं" | The scan must resolve to the right UOM/row unambiguously. |
| **09:23–10:00** | "… बस है कि जो स्कैन करने पर एक न्यू row ऐड हो रही है, उसका Sales Order पर कोई reference नहीं है" | **Core defect: scanned rows have no Sales Order reference.** |
| 10:00–10:14 | "जो न्यू row ऐड हो रही है, उसका Sales Order reference हो ताकि वो item से मैच कर जाए" | The new row must carry the Sales Order reference. |
| 10:14–10:23 | "नौ बॉक्स डिलीवर कर दिया और एक बॉक्स कम … तीन पीस और डिलीवर कर दिया, तो वह तीन पीस भी कम होना हमारे Sales Order में" | The extra PCS must also count against the Sales Order. |
| 10:23–10:38 | "मल्टिपल row होने दो वह कैलकुलेट तब कर लेंगे" | Multiple rows are acceptable. |

---

## 3. Baseline behaviour (read before coding)

| Location | Current behaviour |
|---|---|
| `srv_erp/public/js/package_barcode/stock_scanner.js` → `PackageBarcodeScanner.process_scan()` | Calls `scan_package_barcode`, rejects unknown/duplicate barcodes, then calls inherited `update_table(row_data)`, and for package barcodes calls `add_package_barcode_scan()` which appends a `Package Barcode Scan` child row. |
| `PackageBarcodeScanner.get_row_to_modify_on_scan(item_code, batch_no, uom, barcode, default_warehouse)` | Delegates to `super` (ERPNext `erpnext.utils.BarcodeScanner`) **except** for `Stock Reconciliation`. There is **no Delivery Note branch**. The base implementation matches mainly by item (and UOM), so a scan whose UOM differs from the existing row creates a **new** row — and the base `add_item_to_table` does not set `against_sales_order`/`so_detail`. |
| `srv_erp/package_barcode/api.py` → `scan_package_barcode()` | Returns `PackageBarcodeResolver(...).resolve().as_dict()` → `{package_barcode, barcode, item_code, uom, qty: 1}`; otherwise ERPNext `scan_barcode`. **No Sales Order context.** |
| `srv_erp/package_barcode/service.py` → `PackageBarcodeResolver.resolve()` | Returns the item and the UOM stored on the Package Barcode master; no SO context. |
| `srv_erp/public/js/package_barcode/quantity_control.js` | `enforce_barcode_only_qty()` sets `qty` to the **count of scanned barcodes** (not converted quantities) and only for `Force Barcode Only` items; early-returns for Stock Reconciliation; only handles the `qty` field. |
| `srv_erp/public/js/package_barcode/scan_review.js` | Renders the scan review without UOM / converted-quantity reconciliation. |
| `srv_erp/selling/delivery_note.py` → `validate_sales_order_reference()` / `get_sales_order_items_for_delivery_note()` | The reference rule and the SO-item mapping helper the scan path should reuse. |

---

## 4. Problem statement

1. A package-barcode scan in a Delivery Note can add an item row **without** `against_sales_order`
   / `so_detail`, so the delivery is not attributed to the ordered line.
2. The barcode's UOM is not used to reconcile against an existing convertible row, so BOX and PCS
   barcodes for the same item diverge.
3. `enforce_barcode_only_qty()` counts barcodes, not converted stock quantities.
4. There is no warning when a barcode's UOM cannot be converted to the item's stock UOM.

---

## 5. Required behaviour

1. **Delivery-Note branch.** Add a Delivery Note case to `get_row_to_modify_on_scan` (mirroring the
   existing `Stock Reconciliation` branch) that selects, for the scanned item + barcode UOM:
   a row in this Delivery Note whose UOM equals the barcode UOM → then a convertible row → then an
   empty row.
2. **Always reference the Sales Order.** Any DN item row produced by a scan for an item pending in an
   open Sales Order must carry `against_sales_order` and, when resolvable, `so_detail`. Reuse
   `srv_erp.selling.delivery_note.get_sales_order_items_for_delivery_note()` (or an equivalent
   permission-aware helper). **This is the primary fix.**
3. **Merge into a convertible row.** If the barcode UOM converts into the existing row's UOM, increment
   that row (per DN-001 §4.2, the row's UOM is sticky to its first use). Do not create a duplicate row.
4. **Converted quantity, not barcode count.** A scan adds the scanned package quantity converted to the
   row's UOM/stock UOM (1 PCS barcode → 1 PCS; 1 BOX barcode → `conversion_factor` PCS). Fix
   `enforce_barcode_only_qty()` accordingly.
5. **New row only when necessary.** If the UOM is not convertible, create a second row that still carries
   the Sales Order reference (multiple rows are explicitly allowed).
6. **No-conversion warning**, consistent with DN-001 §4.6.
7. **Scan review shows UOM + converted quantity** so the operator can verify a BOX vs PCS scan.
8. **Do not regress** the Stock Reconciliation/Stock Entry branches or `Force Barcode Only`.

---

## 6. Affected files (expected)

- `srv_erp/public/js/package_barcode/stock_scanner.js` — Delivery Note branch.
- `srv_erp/public/js/package_barcode/quantity_control.js` — UOM-aware scanned quantity.
- `srv_erp/public/js/package_barcode/scan_review.js` — UOM + converted quantity display.
- `srv_erp/package_barcode/api.py` / `service.py` — only if the resolve payload must carry conversion detail.
- `srv_erp/selling/delivery_note.py` — reuse/re-export the SO item mapping helper.
- `srv_erp/tests/test_package_barcode.py` — extend.

---

## 7. Ordered implementation checklist

1. [ ] Read `stock_scanner.js`, `quantity_control.js`, `scan_review.js`, `package_barcode/api.py`,
       `service.py`, and `selling/delivery_note.py` at the baseline.
2. [ ] Implement the Delivery Note branch in `get_row_to_modify_on_scan`.
3. [ ] Wire Sales Order reference resolution into scanned-row creation (**primary fix**).
4. [ ] Make the scanned quantity UOM-aware; reuse the DN-001 conversion helper.
5. [ ] Update the scan review rendering.
6. [ ] Add the no-conversion warning.
7. [ ] Add tests for box scan, pcs scan, mixed scans, unconvertible UOM, and a Stock Reconciliation regression.
8. [ ] `bench build --app srv_erp`; run the targeted tests.
9. [ ] Open the PR with evidence and answers to §8.

---

## 8. Open questions

**Q1 — Which Sales Order to attribute to.** If several open Sales Orders for the customer contain the
scanned item, which line should the scan target? **Recommendation:** prefer an existing referenced row in
the current Delivery Note, otherwise create a referenced row and let the user pick.

**Q2 — Partial-box scanning.** Confirm a partial box is always a separate PCS scan rather than a
partial-quantity box scan.

**Q3 — Duplicate scan policy.** Confirm the existing "already scanned in this document" rejection stays
as-is with mixed-UOM rows.

**Q4 — Multi-UOM prompt.** For the `07:08–07:52` "three combinations" case, is the prompt a Delivery Note
front-end dialog owned by this ticket, or by DN-001's ambiguous-UOM rule?

---

## 9. Definition of done

- A scanned row in a Delivery Note references the Sales Order line and matches the ordered item.
- BOX and PCS barcodes for the same item update the correct row with converted quantities.
- An unconvertible barcode UOM is blocked with a clear message.
- The scan review shows UOM and converted quantity.
- Stock Reconciliation and Stock Entry scanning are unchanged.
- Tests pass; the PR records the commands run and answers §8.

---

## Appendix A — Clean transcript excerpt (source of truth)

Audio: `WhatsApp Audio 2026-10-14 at 6.21.22 AM.mp4`, 867.8 s. Relevant segments (high-accuracy `large-v3`):

```
[00:03:40] ... तो जो आइटम स्कैन कर रहा है तो उसके बार कोर्ड में पैकेज UOM में जो यह है वहीं यूज़ बनाते हुए, बस उसमें एक चीज है ...
[00:04:07] ... मान लीजिए box में था और package बार कोड में box में था
[00:04:13] तो जो original pieces में order था वो row को रखेगा
[00:04:17] और box वाली जो barcode scan हुआ है उसकी row अलग नहीं बना देगा
[00:04:22] आप कह रहे हैं कि जो पहले row already है उसका जो UOM है
[00:04:26] अगर वो UOM convertible है तो वो उसमें ही add करते
[00:04:48] ... जो UOM जो पैकेज बारकोड में उसी UOM ...
[00:05:30] ... मेरा Sales Order में है बॉक्स में और मैं जब आ रहा हूं DN में मैंने पहले करा स्कैन नंबर वाला और मैंने बॉक्स वाला ... तो मुझे कैसे पता देगा कि कौन सा वह चाह रहे हैं
[00:09:23] ... मल्टिपल row का इशु बस है कि जो स्कैन करने पर एक न्यू row ऐड हो रही है, उसका Sales Order पर कोई reference नहीं है
[00:10:00] ... जो न्यू row ऐड हो रही है, उसका जो Sales Order reference हो ताकि वो आइटम से मैच कर जाए
[00:10:14] ... नौ बॉक्स डिलीवर कर दिया और एक बॉक्स कम पड़ रहा था तो उसकी ज़रूरत तीन पीस और डिलीवर कर दिया, तो वह तीन पीस भी कम होना हमारे Sales Order में
[00:10:23] ... मल्टिपल row होने दो, वह कैलकुलेट तब कर लेंगे ...
```

Full transcript and `.srt` retained by the requester.
