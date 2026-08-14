# Approval-gated dynamic Item variants

The Masters module resolves an existing ERPNext Item variant or stages exactly one disabled variant from requested parameters. New variants become usable only after another user with the configured approver role approves the request.

## Safe rollout

The migration intentionally applies these defaults:

- dynamic requests are disabled until roles and profiles are reviewed;
- approval enforcement is enabled;
- Cartesian-product and Brand-triggered bulk variant creation are disabled;
- existing Items and variants are not changed.

To activate requests, assign `Masters Item Requester` and `Masters Item Approver` to different System Users, review **Masters > Dynamic Variant Profiles**, then enable **Dynamic Item Requests** in **Masters Settings**. At least one enabled approver other than the requester is required whenever a new approval request is created.

Every discovered editable child table whose `item_code` is a Link to Item is registered in Masters Settings. The configuration refresh action discovers grids added by future apps or customizations.

## API

All methods use the authenticated Frappe session and enforce configured roles.

Resolve an existing variant or stage a request:

```text
srv_erp.masters.dynamic_item.api.resolve_or_request_item_variant
```

Example `payload`:

```json
{
  "template_item": "LED Lamp",
  "attributes": {
    "Brand": "Acme",
    "Colour": "Warm White"
  },
  "uoms": [
    {"uom": "Box", "conversion_factor": 12}
  ],
  "source": {
    "doctype": "Sales Order",
    "fieldname": "items",
    "document": "SAL-ORD-2026-00001"
  }
}
```

Possible outcomes are `existing`, `pending_approval`, and `packaging_approval_required`. Pending results include the staged Item code and request name but must not be placed into a transaction row.

Supporting methods:

```text
srv_erp.masters.dynamic_item.api.get_dynamic_variant_options
srv_erp.masters.dynamic_item.api.preview_dynamic_item_variant
srv_erp.masters.dynamic_item.api.get_dynamic_item_request_status
srv_erp.masters.dynamic_item.api.approve_dynamic_item_request
srv_erp.masters.dynamic_item.api.reject_dynamic_item_request
srv_erp.masters.dynamic_item.api.cancel_dynamic_item_request
```

Approval and rejection are idempotent for their own terminal state. Rejection and cancellation retain the immutable request audit record, delete the disabled staged Item, and safely remove categorical schema that was created only for rejected requests.

## Invariants

- Variant identity is the canonical template plus sorted attribute/value pairs.
- Packaging UOMs are Item data, never part of variant identity.
- Numeric attributes must be configured on the template before use.
- A pending Item is disabled and blocked by transaction validation.
- Request attributes, packaging, source, state, and staged Item parameters are immutable.
- A requester cannot approve their own request.
- Duplicate active identities and exact packaging requests reuse the existing request.
- Overlapping packaging requests and conflicting conversion factors are rejected.
- Direct, quick-entry, report-driven, Brand-triggered, and bulk variant creation paths are blocked while approval enforcement is active.
