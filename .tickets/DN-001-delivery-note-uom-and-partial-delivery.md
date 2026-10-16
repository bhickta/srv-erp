# Ticket DN-001 — Delivery Note UOM conversion, quantity entry, and multi-row Sales Order accounting

**App:** `srv_erp` (custom Frappe/ERPNext app, repo `github.com/bhickta/srv-erp`)
**Baseline:** `origin/version-15` @ `1898613` (Merge PR #85 `feat/delivery-note-barcode-scanning`)
**Status:** Implemented together with the related Delivery Note ticket. Automated validation passes; PR review pending. Decisions and executed checks: [validation record](../docs/delivery-note-uom-validation.md).

---

## 1. Summary

The Delivery Note must let a warehouse user deliver a Sales Order line that was **ordered in a
packaging UOM** (for example **BOX**) while the goods are physically counted in the **stock UOM**
(for example **PCS**), without breaking the Sales Order's quantity accounting.

The requester's worked example voice note (2026-10-14) is:

- `1 BOX = 20 PCS`.
- The Sales Order line is `1.5 BOX`.
- The operator sends `/ enters` **30 PCS**.
- The **front end must show 30 PCS**; the **back end must compute on the 1.5 BOX conversion**.
- `UOM` must stay consistent ("कुछ और break होना हमारी chain में" — nothing should break the chain).
- Decimal entries like `1.5` must be allowed.
- If the entered UOM is **outside** the item's conversion set, the system must **error**, not silently compute.
- Where the same item is delivered as a mix (for example `9 BOX` + `3 PCS`), **multiple rows are allowed**;
  the shortfall pieces must still **count against the Sales Order**.

---

## 2. Source evidence

Audio: `WhatsApp Audio 2026-10-14 at 6.21.22 AM.mp4` (867.8 s). Timestamps are from the
high-accuracy transcript (Appendix A).

| Time | Statement (cleaned) | Requirement extracted |
|---|---|---|
| 00:00:00 | "जो हमारा Delivery Note है उसमें UOM का बड़ा issue आ रहा है" | Delivery Note UOM is the core problem. |
| 00:51–01:17 | "एक बॉक्स में 20 पीस है … मैंने तीस पीस भेजे तो यह 1.5 हुआ … मैं 1.5 बॉक्स की एंट्री करवाऊंगा क्योंकि मेरे Sales Order में 1.5 बॉक्स है … UOM जो है कुल रखना पड़ेगा" | 1 BOX = 20 PCS example; SO is 1.5 BOX; UOM must be maintained. |
| 01:25–01:33 | "डेसिमल में एंट्रीज़ अलॉव कर देंगे … कुछ और break होना हमारी chain में" | Allow decimal quantities; do not break the chain. |
| 01:56–02:10 | "उसने दो बॉक्स चाहिए तो कनवर्ट हो जाएगा अपने आप पीसेज़ …" | Auto-convert BOX ↔ PCS. |
| 02:10–02:22 | "वह बॉक्स में चला जाएगा पर जब कर रहा है वह 30 पीस लिख रहा है … बैकएंड में एक और पॉइंट फाइव के साथ calculate करेगा और फ्रंट एंड में 30 पीस दिखना चाहिए" | **Front end shows 30 PCS; back end computes on 1.5 BOX.** |
| 02:30–02:57 | "अगर कंवर्ट नहीं हो रही और उसने यूनिट डालिया और वह कंवर्जन से बाहर है तो वह एरर देगा" | Error when the UOM is outside the conversion set. |
| 05:59–06:04 | "अगर हम सिर्फ quantity को अपडेट कर दें … quantity वाला कॉलम" | Only the quantity column is updated. |
| 06:21–06:58 | "जो already UOM use हो रहा है row में … अगर पहले बॉक्स स्कैन कर दिया और बाद में नंबर कर रहा है तो बॉक्स में रखूं … अगर नंबर पहले और बाद में बॉक्स तो नंबर में कर दो" | **A row's UOM is the UOM first used/scanned for that row.** |
| 06:58–07:05 | "at the end बस quantity वाला column ही update करना है और final calculation submit होने के बाद … quantity के साथ use होगा" | Only quantity changes; final calculation happens on submit. |
| 07:08–07:52 | "अगर मेरे पास तीन कंबिनेशन है … मैं DN पूछूँगा कि किस में कनवर्ट करना … DN में एक लाइन आइटम कोड एक ही बार आ सकता है तो आप बताओ कि किसमें रखना" | When one item has several UOMs, the DN must **ask/decide which UOM to keep**. |
| 09:09–10:23 | "पांच बॉक्स … और उसके साथ 3 पीस … तो दो यूनिट बनेगी" | `5 BOX + 3 PCS` legitimately produces two rows. |
| 09:23–10:14 | "नौ बॉक्स डिलीवर कर दिया और एक बॉक्स कम पड़ रहा था तो तीन पीस और डिलीवर कर दिया … वह तीन पीस भी कम होना हमारे Sales Order में" | The extra PCS portion must reduce the Sales Order's pending quantity. |
| 10:23–10:38 | "मल्टिपल row होने दो वह कैलकुलेट तब कर लेंगे" | Multiple rows are allowed; totals are computed afterwards. |

---

## 3. Baseline behaviour (read before coding)

| Location (on `origin/version-15` @ `1898613`) | Current behaviour |
|---|---|
| `srv_erp/selling/delivery_note.py` → `make_delivery_note()` | Overrides ERPNext; sets `qty = 0`, `stock_qty = 0` on newly added rows (DN opens at zero). |
| `srv_erp/selling/delivery_note.py` → `prepare_delivery_note_quantities()` | On submit, drops zero-qty rows; on draft, `doc.flags.allow_zero_qty = True`. |
| `srv_erp/selling/delivery_note.py` → `remove_zero_quantity_items_on_submit()` | Second zero-quantity guard. |
| `srv_erp/selling/delivery_note.py` → `validate_sales_order_reference()` | Requires `against_sales_order` for items pending in an open Sales Order. |
| `srv_erp/selling/delivery_note.py` → `get_sales_order_items_for_delivery_note()` | Returns `item_code, so_detail, against_sales_order, qty, uom, stock_uom, conversion_factor, warehouse` per SO row. |
| `srv_erp/package_barcode/service.py` → `get_item_uom_conversion_factor(item_code, uom)` | The conversion primitive; throws when the UOM is not configured for the item. **Reuse this.** |
| `srv_erp/package_barcode/service.py` → `get_item_uom_options(item_code)` | Lists an item's UOMs (stock UOM first). |
| `srv_erp/selling/sales_order_uom.py` → `get_sales_order_uom()` | Resolves `Item Group.custom_sales_order_uom` up the tree; the Sales Order forces it on rows. |
| `srv_erp/srv_erp/report/items_ordered_in_date_range/*` | Confirms the canonical stored form `stock_qty = qty × conversion_factor` and the `SO UOM` / `Stock UOM` display pattern. |

**Gap:** nothing in the Delivery Note enforces or reconciles UOM conversions, nothing displays the
stock-UOM equivalent, and nothing aggregates multiple rows against one Sales Order line.

---

## 4. Required behaviour

1. **Conversion primitive.** Reuse `get_item_uom_conversion_factor()`; do not re-implement UOM lookup.
2. **Row UOM is sticky to its first use.** A row's `uom` is whichever UOM is first entered/scanned into
   that row. Switching later does not silently flip the row's UOM; the quantity is converted instead.
3. **Stock quantity is canonical.** For every row, `stock_qty = flt(qty) × flt(conversion_factor)`,
   where `conversion_factor` converts the row UOM to the item stock UOM.
4. **Display the stock-UOM equivalent.** The grid must surface the delivered quantity in the stock UOM
   (the "front end shows 30 PCS" requirement) while the stored row keeps the Sales Order's UOM and
   conversion (the "back end computes on 1.5 BOX" requirement). Answer §6 Q1 for the exact storage
   contract before coding.
5. **Decimal quantities allowed.** `qty = 1.5` (BOX) must be accepted and must not be coerced to an
   integer or rejected by grid precision.
6. **Out-of-conversion error.** If the chosen UOM has no conversion to the item's stock UOM, block with a
   clear message (requirement at 02:30–02:57). Never default the factor to 1.
7. **Multiple rows per Sales Order line.** Several DN rows may reference the same `so_detail`.
   The sum of their `stock_qty` must reduce the Sales Order's pending quantity; it must not exceed it.
   Exceeding it is a blocking error naming the item and the Sales Order.
8. **Preserve Sales Order linkage.** Rows created for an ordered item keep `against_sales_order`
   (and `so_detail` when known) so `validate_sales_order_reference()` passes and `delivered_qty`
   updates correctly.
9. **Only quantity changes.** The conversion updates quantity and its derived conversion fields only;
   do not rewrite other columns.
10. **Zero-quantity draft behaviour** in `make_delivery_note()` / `prepare_delivery_note_quantities()`
    must not regress.
11. **Ambiguous multi-UOM case.** Where an item would need more than one UOM on a single DN line and the
    target is ambiguous, the system must **ask the user which UOM to keep** rather than guessing
    (requirement at 07:08–07:52). Prefer a deterministic default only when the Sales Order or the first
    scan makes it unambiguous.

---

## 5. Affected files (expected)

- `srv_erp/selling/delivery_note.py` — conversion helpers, per-`so_detail` aggregation, hook wiring.
- `srv_erp/hooks.py` — only if a new Delivery Note hook entry is required.
- `srv_erp/package_barcode/service.py` — only if the conversion helper must be exported/shared.
- `srv_erp/public/js/delivery_note.js` — **new** file for UOM display/selection (none exists today;
  only `delivery_note_list.js`). Register under `doctype_js["Delivery Note"]`.
- `srv_erp/tests/test_delivery_note_uom_conversion.py` — **new**.
- `srv_erp/tests/test_delivery_note_sales_order_reference.py` — extend if reference rules change.

---

## 6. Open questions (answer before/while implementing)

**Q1 — Storage vs display contract.** Two workable models:
   - **(a)** store `uom = BOX, qty = 1.5, conversion_factor = 20, stock_qty = 30` and *display* the
     PCS equivalent (read-only column). Matches the Sales Order row exactly. **Recommended.**
   - **(b)** store `uom = PCS, qty = 30, conversion_factor = 1, stock_qty = 30`, linked to the BOX SO line.
     Matches the literal "front end shows 30 PCS" wording but diverges from the Sales Order UOM.
   Confirm with the requester.

**Q2 — Which UOM do the DN rows default to** on creation from a Sales Order: the Sales Order UOM (current)
or the item stock UOM?

**Q3 — Rounding/precision** for decimal BOX quantities when converting to PCS (and back). Use the UOM's
configured precision.

**Q4 — Returns.** Confirm `is_return` Delivery Notes are out of scope (existing guards early-return).

**Q5 — Six-row ambiguity limit.** The requester describes "तीन combinations". Confirm how many
same-item/different-UOM rows are acceptable before the DN must force a single UOM.

---

## 7. Ordered implementation checklist

1. [x] Read `selling/delivery_note.py`, `package_barcode/service.py`, `selling/sales_order_uom.py`, and the `hooks.py` Delivery Note entries at the baseline.
2. [x] Resolve §6 Q1/Q3 and record the decision in the PR.
3. [x] Add a pure helper (for example `resolve_delivery_uom_conversion(item_code, uom)`) returning `(stock_uom, conversion_factor)` or raising a clear error.
4. [x] Recompute `stock_qty` for every row on validate.
5. [x] Add per-`so_detail` aggregate validation (delivered stock qty ≤ pending).
6. [x] Add the out-of-conversion error and decimal support.
7. [x] Add the stock-UOM display and the ambiguous-UOM prompt per Q1/Q5.
8. [x] Write tests (§8) and run them on a disposable site.
9. [x] Lint/format and `bench build --app srv_erp`.
10. [x] Open the PR with commands run, results, and each open question answered.

---

## 8. Test matrix

| Area | Required cases |
|---|---|
| Conversion | BOX→PCS resolves; stock-UOM row factor is 1; unknown/outside UOM raises the clear error; factor never silently 1 |
| Quantity math | `stock_qty == qty × conversion_factor`; BOX 1.5 and PCS 30 both give `stock_qty == 30` |
| Decimal | `qty = 1.5` accepted; precision respected |
| Row UOM stickiness | BOX scanned first → row stays BOX; PCS first → stays PCS |
| Multi-row | `9 BOX + 3 PCS` accepted; sum counts to the SO; over-delivery rejected; exact delivery allowed |
| Zero rows | Draft keeps `qty = 0`; submit drops them; all-zero DN raises the existing error |
| Reference | Rows keep `against_sales_order`; unreferenced pending item still triggers `validate_sales_order_reference()` |
| SO state | After submit, SO `delivered_qty`/`delivery_status` match converted stock qty from **all** rows; no double counting |
| Regression | Existing `test_delivery_note_sales_order_reference.py` passes unmodified |

```sh
bench --site <test-site> run-tests --app srv_erp --module srv_erp.tests.test_delivery_note_uom_conversion
bench --site <test-site> run-tests --app srv_erp --module srv_erp.tests.test_delivery_note_sales_order_reference
bench build --app srv_erp
```

---

## 9. Manual acceptance script

1. Item `stock_uom = PCS` with `1 BOX = 20 PCS`.
2. Sales Order line for 1.5 BOX (UOM rule may force BOX).
3. Delivery Note from the Sales Order; rows open at 0.
4. Enter 30 PCS (or switch the row to PCS and enter 30). Confirm the row's stock quantity is 30 and
   the Sales Order delivered quantity becomes 30 PCS / 1.5 BOX.
5. Second DN on a 10 BOX order: `9 BOX` on one row + `3 PCS` on a second row referencing the same SO
   line. Confirm total delivered = 183 PCS and that the 3 PCS reduces the SO pending quantity.
6. Attempt over-delivery across the two rows; confirm rejection.
7. Enter a UOM outside the conversion set; confirm the clear error.
8. Submit; confirm zero rows are dropped and the SO status updates.

---

## 10. Definition of done

- BOX-ordered lines can be delivered as PCS with correct stock quantities and display.
- Decimal quantities work; out-of-conversion UOMs error clearly.
- Multiple rows per SO line are supported and aggregate-validated; the extra PCS reduces the SO.
- Row UOM follows the first use; only quantity changes; submit-time calculation is correct.
- No regression to zero-quantity draft behaviour or the Sales Order reference rule.
- New tests pass on a disposable site; the PR lists the commands run.
- Every question in §6 is answered or explicitly deferred.

---

## Appendix A — Clean transcript excerpt (source of truth)

Audio: `WhatsApp Audio 2026-10-14 at 6.21.22 AM.mp4`, 867.8 s. High-accuracy transcription (`faster-whisper large-v3`, `language=hi`, `beam_size=5`, VAD), relevant segments:

```
[00:00:00] उसके बारे में बात करनी थी, जो हमारा Delivery Note है उसमें UOM का बड़ा इश्यू आ रहा है।
[00:00:51] मेरा अगर फॉर एक्सांपल बॉक्स एक बॉक्स में 20 पीस है और जो मेरा ऑर्डर है वह दो बॉक्स का ...
[00:00:59] ... मैंने तीस पीस भेजे तो यह कितना हुआ वन पॉइंट फाइव ...
[00:01:09] ... मैं 1.5 बॉक्स की एंट्री करवाऊंगा क्योंकि मेरा सेल्स ऑर्डर में 1.5 बॉक्स तो मतलब UOM जो है कुल रखना पड़ेगा
[00:01:25] ... कुछ और break होना हमारी chain में ... डेसिमल में एंट्रीज़ अलॉव कर देंगे या फिर ...
[00:01:56] ... उसने दो बॉक्स चाहिए तो कनवर्ट हो जाएगा अपने आप पीसेज़ ...
[00:02:10] ... वह बॉक्स में चला जाएगा पर जब कर रहा है वह 30 पीस लिख रहा है ... बैकएंड में एक और पॉइंट फाइव के साथ calculate करेगा और फ्रंट एंड में तो 30 पीस दिखना चाहिए ...
[00:02:30] अगर कंवर्ट नहीं हो रही ना और उसने यूनिट डालिया और वह कंवर्जन से बाहर है तो वह एरर देगा ...
[00:05:59] अगर हम सिर्फ quantity को अपडेट कर दें जो उसका quantity वाला कॉलम है उसको अपडेट
[00:06:21] तो आप देखते हैं कि जो अलड़ी UOM यूज़ हो रहा है row में, मान लीजिए एक आइटम है ... और वो पीसेज़ के साथ है ...
[00:06:33] अगर एक ने पहले बॉक्स स्कैन कर दिया और बाद में नंबर कर रहा है तो मैं बॉक्स में रखूं ...
[00:06:53] ... अगर नंबर में है पहले स्कैन करावा और बाद में बॉक्स करावा तो नंबर में कर दो ... at the end बस quantity वाला column ही update करना है
[00:06:58] और final calculation तो submit होने के बाद तो ही जाएगी quantity के साथ use होगा
[00:07:08] अगर मेरे पास तीन कंबिनेशन है ... तो मैं DN पूछूँगा कि किस में कनवर्ट करना ... DN में एक लाइन आइटम कोड एक ही बार आ सकता है तो आप बताओ कि किसमें रखना
[00:09:09] ... हमारे पास पांच बॉक्स ... और उसके साथ 3 पीस ... तो दो यूनिट बनेगी ...
[00:09:23] ... उन्होंने नौ बॉक्स डिलीवर कर दिया और एक बॉक्स कम पड़ रहा था तो उसकी ज़रूरत तीन पीस और डिलीवर कर दिया तो वह तीन पीस भी कम होना हमारे Sales Order में
[00:10:23] ... मल्टिपल row होने दो वह कैलकुलेट तब कर लेंगे ...
```

Full transcript (`.txt`) and timestamped `.srt` are retained by the requester.
