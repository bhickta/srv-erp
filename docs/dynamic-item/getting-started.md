# Getting started with Dynamic Item Approval

## Before you begin

You need:

- an enabled System User account;
- a requester role configured in **Masters Settings**;
- access to the transaction or Item template you are working with;
- an enabled Dynamic Variant Profile for the selected Item template;
- at least one enabled approver who is a different user from you.

If **Resolve / Request Item** or **Request Variant** is not visible, see [Troubleshooting](troubleshooting.md#the-resolve--request-item-button-is-not-visible).

## A five-minute walkthrough

Assume the template is `LED Lamp` and you need:

- Brand: `Acme`
- Colour: `Warm White`
- Packaging: `Box`, conversion factor `12`

### 1. Open the request dialog

Use either route:

- On a configured draft transaction, find its Item table and click **Resolve / Request Item**. Select `LED Lamp`, then click **Next**.
- On the `LED Lamp` Item template, choose **Create > Request Variant**.

### 2. Enter variant identity

In **Configure LED Lamp**, enter the requested values under **Variant Identity**.

The form indicates which fields are required. For a categorical field, either select an existing value or type a new value only when the field description says new values are allowed.

### 3. Enter packaging if required

Under **Packaging UOMs**, add:

| UOM | Conversion Factor |
| --- | ----------------: |
| Box |                12 |

The UOM itself must already exist in the UOM master. A conversion factor must be a positive number.

### 4. Resolve or submit

Click **Resolve / Request**.

The result depends on current Item master data:

| Situation                                                 | Result                                                                                  |
| --------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| The enabled variant and requested packaging already exist | The Item is returned immediately. On a transaction, it is inserted into the Item table. |
| The enabled variant exists but packaging is missing       | An **Add Packaging** request is submitted. No new Item is created.                      |
| The variant does not exist                                | A **Create Variant** request and a disabled staged Item are created.                    |
| The same request is already pending                       | The existing pending request is returned.                                               |

For a pending result, the message **Approval Required** contains a link to the Dynamic Item Request and may show the staged Item code.

### 5. Wait for another user to review

An approver opens the request from their assignment or from **Masters > Pending Item Requests**. They approve it or reject it with a reason.

### 6. Continue the transaction after approval

Approval does not silently modify the transaction from which the request was made.

Return to the draft transaction, click **Resolve / Request Item**, and enter the same template and parameters. Because the Item is now approved, it is resolved immediately and placed in the Item table.

## What you can safely do while waiting

- Keep the source transaction in Draft.
- Open the request link to view its current status.
- Cancel your own pending request if it is no longer needed.
- Contact an approver if the request is urgent or the assignment notification was missed.

Do not manually enable the staged Item, edit its attributes or UOMs, or copy its Item code into a transaction. These changes are blocked to preserve the approval record.

## Next steps

- Requesters: continue with the [Requester guide](requester-guide.md).
- Approvers: continue with the [Approver guide](approver-guide.md).
- Masters administrators: complete the [Administrator guide](administrator-guide.md).
