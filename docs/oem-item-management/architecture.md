# OEM Catalog boundaries and decisions

OEM Catalog is an independent module inside SRV. ERPNext owns inventory, commercial documents, accounting, and manufacturing. The pure domain imports no Frappe, ERPNext, or legacy SRV service. Application commands orchestrate domain validation through narrow persistence, authorization, Item, pricing, and barcode adapters.

## Physical identity

Identity is a canonical UTF-8 JSON payload, hashed with SHA-256. It contains the stable Product ID, immutable identity namespace, stock UOM, and every required physical attribute. Customer, company, price, quantity, profile/revision numbers, and labels are context/audit only. Unknown is never a wildcard or not-applicable. Decimal inputs are precise strings. Printed text uses NFC and trims boundary whitespace while preserving case. Hash matches also compare canonical bytes.

Published schema identity roles and keys remain fixed. A revised default does not remap historical specifications. Physically different branding, colour, stickers, artwork, design, certification marks, or package composition have distinct identities where classified as physical.

## Transactions and privilege

Requests create OEM records only. Approval locks Specification then Request and materializes one standalone Item through the installed normal Item controller, with a narrow allowlist. The command's scoped privilege cannot be used by ordinary REST or propagated to searches. No opening stock, valuation, prices, barcode rows, BOM, or variant attributes are copied. Binding uniqueness is database-enforced. Maker-checker is required by default.

Command receipts are actor/operation/UUID scoped. Processing receipts exist only in the current transaction; every committed receipt is Completed. Receipt, Item, binding, decision, audit, and outbox roll back together. Commands never commit from document events. Notifications run separately from inventory consistency.

## Packaging and legacy adoption

Every Item/UOM factor is positive and fixed. Physical composition belongs to identity where classified; transaction quantity does not. A second Box factor cannot replace the first. Adoption writes new OEM metadata only after complete reviewed evidence and source fingerprint comparison; it never changes an existing Item. Drift blocks new use; quarantine never rewrites source stock.

## Sales Order composition

The OEM Sales Order subclass inherits ERPNext's existing controller. It calls ordinary validation and suppresses only the parent `items` mandatory error on a validated all-pending draft. Real rows still require concrete Items. Pending lines persist in a separate child table and never create demand or official totals. Unresolved intent blocks submission. Approval never saves an order: an explicit Apply and subsequent user save bind the real row.

Existing Item, Item Price, and Stock Entry overrides remain registered. Commercial/customer-history approval is separate. Kill switches stop new OEM commands; already created ordinary Items and historical documents remain usable.

## Readiness and rollout

Physical release, sales price/company defaults, barcode packaging, and manufacturing BOM readiness are separate checks. Missing price is an explicit unavailable state, not zero-price fallback. Install/migration creates metadata and disabled settings only, without global role assignments or catalogue import.

Release requires real database atomicity/permission/concurrency tests, migration non-interference, scan-chain compatibility, browser checks, and physical Android/iOS UAT. Operator activation, deployment, adoption of live data, and production decisions are outside this PR.
