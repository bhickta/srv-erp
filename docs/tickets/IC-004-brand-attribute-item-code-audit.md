# Ticket IC-004 — Audit and harden brand + attribute item-code creation

**Type:** Review/hardening handoff for a coding agent
**App:** `srv_erp` (custom Frappe/ERPNext app, repo `github.com/bhickta/srv-erp`)
**Baseline:** `origin/version-15` @ `1898613`
**Status:** Specification only. No application code was changed, no migration was run, and no tests were
executed while preparing this document.

---

## 1. Summary

The audio note ends with a caveat about the **brand + attribute based item-code creation**: the work was
handed to a developer, it is "rough", it has problems, and the requester is fixing it in parallel and
wants it reviewed.

This ticket is a **review + hardening** task: verify that item codes generated from a Brand and its
attributes are deterministic, collision-safe, correctly abbreviated, covered by tests, and documented —
and fix what fails.

---

## 2. Source evidence

Audio: `WhatsApp Audio 2026-10-14 at 6.21.22 AM.mp4` (867.8 s); timestamps from the high-accuracy
transcript (Appendix A).

| Time | Statement (cleaned) | Meaning |
|---|---|---|
| 13:32–14:15 | "… जो हमारा plan था item code creation का … कि मेरा brand और attribute के base पर … तो वह मैंने [किसी] को दिया, उस पर अगर check करना तो करना, पर उसमें बहुत दिक्कत है … मैं वह भी ठीक कर रहा हूँ साथ-साथ … brand में हमारा brand से … जो item बन जाए … यह rough चीज़ है और देखना पड़ेगा" | Item-code creation from Brand + attributes was delegated; it is rough, has problems, and needs review. |

> Unlike DN-001/DN-002/PP-003, the audio gives **no concrete defect list** here. The first deliverable
> of this ticket is therefore to **produce that list from the code and a test run**, not to assume one.

---

## 3. Baseline and existing building blocks (read before coding)

| Location | Relevance |
|---|---|
| `srv_erp/masters/dynamic_item/staging.py` | Builds the variant via ERPNext `get_variant(...)`; throws `DynamicItemConflict` when the generated `item_code` already exists, telling the user to "review attribute abbreviations". |
| `srv_erp/item/variant_auto_creation.py` | Brand create/update/delete handling and Item Attribute brand source. |
| `srv_erp/masters/dynamic_item/brand_rules.py`, `brand_rules_api.py`, `brand_rule_resolution.py`, `brand_rule_sync.py`, `brand_rule_conflicts.py` | Brand rule configuration, publication, resolution, sync, and conflict reporting. |
| `srv_erp/masters/dynamic_item/brand_value_sync.py`, `brand_default_backfill.py` | Value resolution/synchronisation for variants; both reference generated item codes and collision checks. |
| `srv_erp/masters/dynamic_item/normalization.py`, `signatures.py`, `packaging.py`, `profile.py` | Normalisation (incl. UOM canonicalisation), variant signatures, packaging rows, variant profile. |
| `srv_erp/masters/dynamic_item/guard.py`, `approval_flow.py`, `request_flow.py`, `service.py` | Dynamic-item request/approval lifecycle — item codes are staged and then resolved. |
| `srv_erp/masters/dynamic_item/cleanup.py` | Reconciles `resolved_item` against requests. |

Item codes are produced by ERPNext from attribute abbreviations; the app layers approval, conflict, and
sync behaviour around that.

---

## 4. Required behaviour / deliverable

1. **Defect inventory first.** Read the modules above and run the existing dynamic-item tests on a
   disposable site. Produce a written list of concrete defects/risks for brand+attribute item-code
   creation (this list is the primary deliverable and must be checked in with the PR).
2. **Deterministic names.** The same (Brand, template, attribute values) must always generate the same
   item code, independent of attribute row order or whitespace.
3. **Collision safety.** A generated code that collides with an existing *different* Item must fail with a
   clear, actionable message (the existing `DynamicItemConflict` path) — never silently overwrite or
   duplicate.
4. **Abbreviation contract.** Document how attribute abbreviations feed the item code, where they are
   maintained, and what happens when an abbreviation is missing, ambiguous, or changed after items exist.
5. **Ordering independence.** Reordering attributes/values must not change the generated code.
6. **Approval integration.** Staged item codes must remain consistent through the request/approval/cleanup
   lifecycle (no orphaned or mismatched `staged_item_code` / `resolved_item`).
7. **Tests.** Add/extend tests for determinism, ordering, collisions, missing abbreviations, and the
   approval round-trip.
8. **Docs.** Add a short section to `docs/dynamic-item/` describing the naming scheme and the abbreviation
   maintenance workflow.

---

## 5. Affected files (expected)

- `srv_erp/masters/dynamic_item/staging.py` and related modules — fixes found by the audit.
- `srv_erp/item/variant_auto_creation.py` — only if the audit finds brand/abbreviation defects.
- `srv_erp/tests/` — new/extended dynamic-item tests.
- `docs/dynamic-item/*.md` — naming + abbreviation documentation.
- The checked-in **defect inventory** produced in §4.1.

---

## 6. Ordered implementation checklist

1. [ ] Read `staging.py`, `variant_auto_creation.py`, and the `brand_*` / `normalization.py` /
       `signatures.py` modules at the baseline.
2. [ ] Identify a disposable test site; read the existing dynamic-item tests.
3. [ ] Reproduce and record concrete defects (naming, collisions, abbreviations, ordering, lifecycle).
4. [ ] Fix the defects found; do not refactor beyond the defects.
5. [ ] Add tests for each defect.
6. [ ] Document the naming/abbreviation contract.
7. [ ] Lint/format and `bench build --app srv_erp`.
8. [ ] Open the PR **including the defect inventory** and the evidence (commands + results).

---

## 7. Test matrix

| Area | Required cases |
|---|---|
| Determinism | Same inputs → same code across runs |
| Ordering | Permuting attribute rows does not change the code |
| Collision | Existing different Item → clear `DynamicItemConflict`; same item → idempotent |
| Abbreviations | Missing/duplicate abbreviations produce a clear error, not a truncated/garbled code |
| Approval lifecycle | `staged_item_code` / `resolved_item` stay consistent through approve/reject/cleanup |
| Regression | Existing dynamic-item and brand-rule tests pass |

---

## 8. Open questions

**Q1 — What exactly is broken?** The audio only says "rough / many problems". Confirm the specific pain
points from the requester (or treat the §4.1 defect inventory as the answer).

**Q2 — Naming scheme.** Is the current ERPNext attribute-abbreviation scheme the intended one, or is a
Brand-prefixed/series scheme wanted?

**Q3 — Ownership.** The audio says the work was delegated and is being fixed in parallel. Confirm this
ticket should proceed independently and how to avoid conflicting with the parallel fix.

---

## 9. Definition of done

- A checked-in defect inventory for brand+attribute item-code creation.
- Fixes for the confirmed defects.
- Tests covering determinism, ordering, collisions, abbreviations, and the approval lifecycle.
- Documented naming + abbreviation contract.
- The PR lists the commands run and answers §8.

---

## Appendix A — Clean transcript excerpt (source of truth)

Audio: `WhatsApp Audio 2026-10-14 at 6.21.22 AM.mp4`, 867.8 s. Relevant final segment (high-accuracy `large-v3`):

```
[00:13:27] ... तो यह आप UOM वाला पर UOM पर, बाकी वैसे जो हमारा plan था आइटम कोड क्रिएशन का ...
[00:13:43] ... प्रोडक्शन का ना कि मेरा ब्रांड और एट्रिब्यूट के बेस पर, तो वह मैंने … को दिया, उस पर अगर
[00:13:52] चेक करना तो करना, पर उसमें है बहुत दिक्कत है ... मैं वह भी ठीक कर रहा हूं साथ-साथ ...
[00:13:58] ... ना मतलब हो यह ना कि जो ब्रांड में हमारा ब्रांड से ... जो आइटम बन जाए ... यह rough चीज़ है
[00:14:08] और देखना पड़ेगा ...
```

Full transcript and `.srt` retained by the requester.
