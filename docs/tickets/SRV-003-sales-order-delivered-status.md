# SRV-003: Complete (Delivered) Sales Order status

Priority: 3
Status: Implemented.

Show Complete (Delivered) as a green status on submitted fully delivered Sales Orders, including those still awaiting billing/payment. Use this label in form and list ahead of Approved workflow status. Retain draft/cancelled/closed/on-hold states and reopen the fulfillment display after delivery cancellation/return. Preserve ERPNext billing status and core lifecycle semantics. Historical fully delivered orders display correctly without rewriting documents.

Deliverable: Separate production and dev PRs. Merge dev only after validation; leave production open.

Implementation: Form and list show the green Complete (Delivered) label before the Approved workflow badge on submitted fully delivered orders. Closed/On Hold/Cancelled remain distinct. Clicking the list indicator filters to delivered submitted orders. ERPNext's stored billing lifecycle status, invoice creation and workflow transitions remain intact; this is a fulfillment display alias.

Validation: JavaScript checks pass for form/list, draft/cancelled/held/closed orders, pending billing, normal fallback and delivery reversal. All 5 Sales Order UI Python tests pass. No database changes or data backfill required.
