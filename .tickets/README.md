# srv_erp tickets (local only — not tracked by git)

## Tickets

| File | Scope | Depends on |
|---|---|---|
| `DN-001-delivery-note-uom-and-partial-delivery.md` | Delivery Note UOM conversion, decimal qty, row UOM stickiness, multi-row accounting | — |
| `DN-002-package-barcode-uom-row-targeting.md` | Scanned DN rows must carry a Sales Order reference and correct UOM | DN-001 |
| `PP-003-production-planning-ratio-report.md` | New production-planning report: trailing sales, brand-less, ratio targets + chart | — |
| `IC-004-brand-attribute-item-code-audit.md` | Audit/harden brand + attribute item-code creation | — |

## How to run one

Point the agent at the file and say "implement it":

```
Implement .tickets/DN-001-delivery-note-uom-and-partial-delivery.md

Rules:
1. git fetch origin first; use the baseline named in the ticket. If it moved,
   preserve newer behaviour and say so.
2. Work on a NEW branch off origin/version-15. Do NOT touch the current
   checkout (it has unrelated uncommitted work on
   fix/brand-item-group-default-validation).
3. Answer the open questions in the ticket's final sections before writing code.
   If unsure, ask me or state the assumption explicitly.
4. Follow the ticket's ordered checklist, reuse the modules it names, and run
   the test matrix. Paste raw command output.
5. Do not claim anything you did not run. Stay inside the ticket's scope.
6. Open a PR with: what changed, commands run + results, each open question answered.
```

## How to run all of them

```
Implement every ticket in .tickets/ (DN-001, DN-002, PP-003, IC-004).
Each gets its own branch off origin/version-15 and its own PR. Read each ticket
fully first. Land DN-001 before DN-002, since DN-002 depends on DN-001's
conversion contract. Same rules as above.
```

## Notes

- Tickets are specs only — no code changes are described as already done.
- Each ticket quotes its source voice note with audio timestamps, and lists the
  concrete gaps against the code at the baseline commit.
- The audio is a code-mixed Hindi/English requirements discussion; where it is
  ambiguous the ticket raises an explicit open question instead of guessing.
