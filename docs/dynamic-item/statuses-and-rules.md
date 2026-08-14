# Dynamic Item statuses and business rules

## Request types

### Create Variant

Used when no Item exists for the requested template and attribute/value identity.

While pending, the request normally has a **Staged Item**. The Item is disabled, marked **Pending Approval**, linked to the request, and cannot be used in transactions.

### Add Packaging

Used when an approved, enabled Item exists but lacks one or more requested packaging UOM rows.

The request points to the existing **Resolved Item** and does not create a staged Item or a new identity.

## Request statuses

| Status           | Meaning                                                           | Permitted next action                 |
| ---------------- | ----------------------------------------------------------------- | ------------------------------------- |
| Pending Approval | Waiting for review. Parameters and Item staging are locked.       | Approve, Reject, or requester Cancel. |
| Approved         | The request resolved to an enabled Item or updated its packaging. | None; terminal status.                |
| Rejected         | An approver declined the request and recorded a reason.           | None; submit a corrected new request. |
| Cancelled        | The requester withdrew the request.                               | None; submit a new request if needed. |

The list colours are orange, green, red, and gray respectively.

## Status transitions

```text
                     Approve
                    +-------> Approved
                    |
Pending Approval ---+-------> Rejected
                    |          Reject with reason
                    |
                    +-------> Cancelled
                               Requester cancels
```

There is no reopen or edit transition. A corrected requirement is submitted as a new request.

## Dynamic Item Request fields

| Field                            | Explanation                                                                                       |
| -------------------------------- | ------------------------------------------------------------------------------------------------- |
| Request Type                     | Create Variant or Add Packaging.                                                                  |
| Status                           | Current approval state.                                                                           |
| Item Template                    | Template governing variant identity.                                                              |
| Staged Item                      | Disabled Item proposed by a pending Create Variant request. Cleared after rejection/cancellation. |
| Resolved Item                    | Existing Item targeted for packaging, or final Item after approval.                               |
| Variant Attributes               | Immutable identity parameters requested.                                                          |
| Packaging UOMs                   | Immutable requested UOM conversions.                                                              |
| Canonical Signature              | Stable fingerprint of the canonical identity or packaging request.                                |
| Active Signature                 | Unique reservation held only while the request is pending.                                        |
| Source DocType / Grid / Document | Business location from which the user submitted the request.                                      |
| Requested By / On                | Request audit.                                                                                    |
| Approved By / On                 | Approval audit.                                                                                   |
| Rejected By / On                 | Rejection or cancellation actor and time.                                                         |
| Rejection / Cancellation Reason  | Explanation retained for terminal requests.                                                       |
| Amended From Request             | Reserved link for tracing a replacement request when used by the business process.                |

All request fields and child rows are read-only to users. State changes happen only through the provided actions.

## Item identity rules

Variant identity consists of:

1. the Item template; and
2. the canonical set of attribute/value pairs, sorted consistently by the system.

Identity does not include:

- packaging UOMs or conversion factors;
- transaction quantity, warehouse, price, discount, or delivery date;
- request source or requester;
- Item image.

Consequences:

- changing packaging does not create another Item;
- attribute order does not create another Item;
- case differences reuse an existing master name when one exists;
- repeating the same identity while pending returns the existing request;
- once approved, the same identity resolves directly to its Item.

## Attribute rules

- At least one variant attribute is required.
- A request supports at most 20 attributes.
- An attribute may appear only once, including across profile and additional-attribute inputs.
- Names and values are trimmed and Unicode-normalized.
- Master lookup is case-insensitive.
- Required profile attributes must have values.
- Attributes outside the profile require **Allow New Categorical Attributes**.
- A new value is blocked when its profile row has **Allow New Values** off.
- Disabled Brands cannot be used.
- New categorical attributes may be staged; new numeric attributes may not.

## Numeric attribute rules

- The Item Attribute must already be numeric.
- It must already be attached to the Item template.
- It must be present in the Dynamic Variant Profile.
- The value must satisfy the template's from-range, to-range, and increment.

## Packaging rules

- A request supports at most 10 packaging UOM rows.
- Every UOM must exist in the UOM master.
- A UOM may appear only once per request.
- Every conversion factor must be a finite number greater than zero.
- The stock UOM, if supplied, must have conversion factor `1`.
- An existing identical UOM/factor requires no update.
- An existing UOM with a different factor is a conflict and is never silently overwritten.
- Two pending Add Packaging requests for the same Item cannot overlap on a UOM.

## Existing and disabled Item rules

| Matching Item state         | Behavior                                                                                                      |
| --------------------------- | ------------------------------------------------------------------------------------------------------------- |
| Enabled and approved/legacy | Returned immediately, subject to packaging checks.                                                            |
| Pending dynamic staged Item | Existing pending request is returned.                                                                         |
| Disabled non-pending Item   | Request is blocked; a Masters administrator must decide whether to reactivate or otherwise resolve that Item. |

## Approval and permission rules

- Only users with a configured requester role may resolve/request.
- Only users with the configured approver role may approve or reject.
- The requester cannot approve their own request.
- Only the requester sees the normal **Cancel Request** action for a pending request.
- A new request requires another enabled System User with the approver role.
- Requesters can read their request status; approvers and System Managers can review requests according to DocType access.

## Pending Item protections

A staged Item cannot be manually:

- enabled;
- marked Approved;
- disconnected from its request;
- assigned a different signature or audit user;
- changed to different variant attributes or packaging UOMs.

Any document containing a Link to a pending dynamic Item is rejected during validation while approval enforcement is active. This covers direct Item links and Item links inside child tables.

## Direct and bulk creation rules

While approval enforcement is active:

- direct insertion of a new Item variant is blocked;
- ERPNext Single Variant and Multiple Variants buttons are removed from eligible templates;
- quick-entry variant creation is redirected with instructions to use Resolve / Request Item;
- bulk variant creation and report-driven missing-variant creation are unavailable;
- Brand-triggered automatic variant creation is disabled by rollout defaults.

These controls preserve on-demand creation and prevent reintroducing Item proliferation through another screen.

## Rejection and cancellation cleanup

For Create Variant, termination attempts to remove:

- the disabled staged Item;
- categorical values created only for the rejected request;
- a new Brand created only for the rejected request;
- a new categorical Item Attribute;
- request-created links on the template and Dynamic Variant Profile.

Cleanup never removes an artifact that has been adopted by an approved request, used by an Item variant, shared by another pending request, or referenced elsewhere. Cleanup errors are recorded for administrators without deleting the request audit.
