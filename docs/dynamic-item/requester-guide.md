# Dynamic Item requester guide

This guide is for users who select Items on transactions or request a new variant from an Item template.

## Requesting from a transaction Item table

The feature is available only on transaction Item tables enabled by a Masters administrator.

1. Open a new or editable Draft transaction.
2. In the Item table, click **Resolve / Request Item**.
3. Select an enabled Item template that uses Item Attribute variants.
4. Click **Next**.
5. Complete the **Configure _template_** dialog.
6. Click **Resolve / Request**.

If an approved Item already exists, the system uses the selected blank row when exactly one blank row is selected. Otherwise, it adds a new row and sets its Item code.

If approval is required, no pending Item is placed in the table. Keep the transaction in Draft and use the same flow again after approval.

## Requesting from an Item template

1. Open the Item template.
2. Confirm that **Has Variants** is enabled and **Variant Based On** is `Item Attribute`.
3. Select **Create > Request Variant**.
4. Enter the attributes and optional packaging.
5. Click **Resolve / Request**.

If the Item already exists, its Item form opens. If a request is needed, an **Approval Required** message links to the request.

## Completing the parameter dialog

### Variant identity fields

Profile parameters appear in their configured order.

- A required parameter must have a value.
- A categorical parameter uses an autocomplete list.
- If its description says **Select an existing value or type a new categorical value**, you may enter a new value.
- If its description says **Select an existing value**, use only a listed value.
- A numeric attribute appears as a number field and must follow the range and increment configured on the Item template.

Attribute and value matching is case-insensitive. For example, an existing `Blue` value is reused if `blue` is entered.

### Additional categorical attributes

The **Additional Categorical Attributes** table appears only when **Allow New Categorical Attributes** is enabled.

Use it for a genuine new identity parameter that is not already shown in the dialog. Enter each attribute only once. Do not use it for descriptions, notes, packaging, rates, or other non-identity data.

New numeric attributes cannot be introduced here. A Masters administrator must first configure numeric attributes on the Item template and its Dynamic Variant Profile.

### Packaging UOMs

Each row contains:

- **UOM**: an existing UOM master such as Box, Carton, or Pack;
- **Conversion Factor**: how many stock-UOM units are represented by one unit of that UOM.

Example: if the stock UOM is `Nos`, `Box = 12` means one Box contains 12 Nos.

Rules:

- conversion factors must be finite positive numbers;
- the same UOM cannot appear twice in one request;
- if the stock UOM is included, its conversion factor must be `1`;
- an existing UOM row with a different factor is a conflict and is not overwritten;
- a UOM already covered by another pending packaging request cannot be requested again.

Packaging is not part of Item identity. Do not add attributes such as `Box of 12` merely to represent packaging.

## Understanding the result

### Existing Item

The requested identity already exists as an enabled Item. If all requested packaging is also present, the Item is available immediately and no approval request is created.

### Pending Create Variant

The identity does not exist. The system creates:

- a **Create Variant** Dynamic Item Request;
- a disabled staged Item with the requested identity and packaging;
- an assignment for eligible approvers.

The staged Item cannot be used until approval.

### Pending Add Packaging

The Item exists, but one or more requested packaging UOMs are missing. The system creates an **Add Packaging** request against that Item. It does not create another variant.

## Tracking requests

Open **Masters > Dynamic Item Requests**. The list uses these indicators:

- orange: **Pending Approval**;
- green: **Approved**;
- red: **Rejected**;
- gray: **Cancelled**.

Open a request to review:

- request type and status;
- Item template, staged Item, and resolved Item;
- requested attributes and packaging;
- source DocType, grid, and document when available;
- requester, approver or rejector, timestamps, and reason.

You can view your request, but you cannot edit its recorded parameters.

## Cancelling your request

For your own **Pending Approval** request:

1. Open the Dynamic Item Request.
2. Select **Actions > Cancel Request**.
3. Confirm the cancellation.

Cancellation removes the unreferenced staged Item and request-owned provisional master data when safe. The request remains as a **Cancelled** audit record.

An Approved, Rejected, or Cancelled request cannot be cancelled again.

## Correcting a mistake

Pending request parameters are immutable. If the template, attribute, value, packaging, or source is wrong:

1. Cancel your own pending request, or ask an approver to reject it.
2. Submit a new request with the correct parameters.

Do not ask an administrator to edit the request or staged Item directly.

## Requester checklist

Before clicking **Resolve / Request**, confirm:

- the correct Item template is selected;
- every identity parameter is present and spelled correctly;
- packaging is entered as UOM rows, not as identity attributes;
- conversion factors use the Item's stock UOM as their basis;
- new Brands or values are genuine master data and not typing variations;
- the source transaction can remain in Draft until approval.
