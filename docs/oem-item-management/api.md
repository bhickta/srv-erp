# OEM command contract

The `srv_erp.oem_catalog.api` entry points authenticate, authorize context, enforce POST on mutation, validate strict bounded JSON DTOs, and return v1 results. Server canonicalization and publication tokens are authoritative; client Item IDs, hashes, actors, decisions, and privileged fields are never trusted.

Configuration DTO: `api_version`, `product`, `configuration_token`, `values`, `package_choice`, `context` (customer/company/brand/effective_date), and `source` (allowlisted adapter/document/row intent). Commands take an idempotency UUID. Read preview has no persistence side effects.

Errors use stable codes and localized safe messages; inaccessible record names and raw SQL/tracebacks are not exposed. Version conflicts preserve the user's draft. All application results must be reauthorized when replayed.

Supported adapter contexts are standalone, Sales Order, and barcode. Other source doctypes cannot be posted to a generic writer.
