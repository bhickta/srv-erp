# Dynamic Item approver guide

This guide is for users assigned the approver role configured in **Masters Settings**.

## Finding requests to review

Use either route:

- open the ToDo assignment created for the request;
- open **Masters > Pending Item Requests** or **Dynamic Item Requests**, then filter by **Pending Approval**.

The request list shows request type, status, staged Item, and resolved Item, with orange indicators for pending requests.

If no assignment was received, the request may still exist. Always check the pending request list before concluding that there is nothing to review.

## What to review

Open the Dynamic Item Request and check the following sections.

### Request summary

- **Request Type**: `Create Variant` or `Add Packaging`.
- **Item Template**: the variant template that governs identity.
- **Staged Item**: the disabled Item proposed by a Create Variant request.
- **Resolved Item**: the existing Item targeted by Add Packaging, or the final Item after approval.

### Requested configuration

- Every required business attribute is present.
- Attribute names and values are canonical and free from spelling variants.
- Any new Brand, attribute, or value is valid master data.
- The resulting abbreviation and staged Item code are understandable and non-conflicting.
- Numeric values comply with the template's range and increment.
- Packaging UOMs and conversion factors are operationally correct.

### Request source and audit

- Source DocType, grid, and document provide reasonable business context.
- **Requested By** is the expected user.
- You are not the requester. A requester cannot approve their own request.
- For rework or resubmission, compare the request with its prior rejected or cancelled record if relevant.

## Approving a Create Variant request

1. Open a pending **Create Variant** request.
2. Select **Actions > Approve**.
3. Confirm **Approve this request and make its Item configuration available?**

On approval, the system:

- rechecks the identity under a database lock;
- verifies that the staged Item is still disabled and matches the request;
- verifies its packaging;
- records the approver and approval time;
- changes the Item's approval status to **Approved**;
- enables the Item;
- marks the request **Approved** and closes approval assignments.

If another matching enabled Item was created concurrently, the system safely removes the redundant staged Item and resolves the request to the existing Item.

## Approving an Add Packaging request

1. Open a pending **Add Packaging** request.
2. Confirm the target **Resolved Item** and each conversion factor.
3. Select **Actions > Approve** and confirm.

The system locks the Item, confirms that it remains enabled, adds only the missing UOM rows, saves the Item, and marks the request Approved.

No new Item is created for packaging approval.

## Rejecting a request

1. Open a pending request.
2. Select **Actions > Reject**.
3. Enter a clear **Rejection Reason**.
4. Click **Reject**.

Use a reason that lets the requester correct the next submission, for example:

- `Use existing Brand "ACME" instead of creating "Acme Ltd".`
- `Box conversion factor should be 24, not 12.`
- `Colour is not an approved identity attribute for this template.`

For Create Variant, rejection deletes the disabled staged Item. Provisional categorical attributes, values, template links, profile rows, and Brands are removed only when they were created by rejected requests and have not been approved, adopted, or referenced elsewhere.

The request itself remains as a **Rejected** audit record.

## Maker-checker behavior

- The requester cannot approve their own request, even if they also have the approver role.
- An approver may reject a request submitted by themselves when it must be withdrawn, although requester cancellation is the preferred route.
- At least one other enabled System User with the configured approver role must exist before a new request can be created.
- The Administrator account passes role checks, but normal operations should use named user accounts for a meaningful audit trail.

## Requests that should not be approved

Reject or escalate when:

- the same business Item already exists under a different spelling or code;
- an attribute is descriptive rather than part of Item identity;
- packaging has been represented as an identity attribute;
- a Brand or categorical value violates naming standards;
- the source transaction or business purpose is unclear;
- the conversion factor is unverified;
- the staged Item was manually changed or no longer matches the request;
- approval would create an Item that should remain disabled.

## Approver checklist

Before approving, confirm:

- requester and approver are different users;
- identity is complete, minimal, and canonical;
- no equivalent Item already exists;
- new master data follows governance standards;
- packaging conversion factors are correct;
- the staged Item code and abbreviation are acceptable;
- the source and business need are credible.
