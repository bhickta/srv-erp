# Dynamic Item Approval user guide

Dynamic Item Approval lets users resolve an existing Item variant or request a missing one only when it is needed. A missing variant is staged as a disabled Item and cannot be used in transactions until another authorized user approves it.

This prevents the Item master from being filled with every theoretical combination of brand, colour, size, packing, and other parameters.

## Who should read which guide

- [Getting started](getting-started.md): a short introduction and first-use walkthrough for everyone.
- [Requester guide](requester-guide.md): how to resolve Items, request variants or packaging, track requests, and correct mistakes.
- [Approver guide](approver-guide.md): how to review, approve, and reject requests safely.
- [Masters administrator guide](administrator-guide.md): roles, profiles, settings, Item grids, rollout, and ongoing governance.
- [Statuses and business rules](statuses-and-rules.md): request types, status meanings, Item identity, field definitions, and validation rules.
- [Troubleshooting](troubleshooting.md): common messages, causes, and corrective actions.

## The process at a glance

```text
Enter the required Item parameters
             |
             v
Does an approved, enabled variant already exist?
       | Yes                         | No
       v                             v
Use it immediately          Create a disabled staged Item
                                         |
                                         v
                                Another user reviews it
                                  | Approve     | Reject
                                  v             v
                           Enable and use   Remove staging
```

Packaging follows the same approval principle. If the Item already exists but needs a new packaging UOM, the request changes the existing Item after approval; it does not create another Item variant.

## Key terms

| Term                    | Meaning                                                                                                        |
| ----------------------- | -------------------------------------------------------------------------------------------------------------- |
| Item template           | An ERPNext Item configured with **Has Variants** and **Variant Based On: Item Attribute**.                     |
| Variant identity        | The Item template together with its canonical attribute/value combination.                                     |
| Dynamic Variant Profile | The allowed and required parameters for one Item template.                                                     |
| Packaging UOM           | An alternate UOM and its conversion factor, such as `Box = 12 Nos`. Packaging is not part of variant identity. |
| Staged Item             | A disabled Item created for a pending **Create Variant** request. It is visible for review but cannot be used. |
| Dynamic Item Request    | The permanent request and approval audit record.                                                               |
| Requester               | A user allowed to resolve Items and submit new requests.                                                       |
| Approver                | A user allowed to approve or reject requests. The requester cannot approve their own request.                  |

## Where to find the feature

Open the **Masters** workspace. Its main links are:

- **Pending Item Requests** and **Dynamic Item Requests** for request review and tracking;
- **Masters Settings** and **Dynamic Variant Profiles** for configuration;
- **Items**, **Item Templates**, **Item Attributes**, **Brands**, and **UOM** for related masters;
- **Variant Coverage** for the existing coverage report.

On configured draft transaction forms, the Item child table shows **Resolve / Request Item**. On an eligible Item template, the **Create** menu shows **Request Variant**.

## Important operating principles

- Approval is maker-checker: the requester and approver must be different users.
- Pending staged Items stay disabled and are rejected by transaction validation.
- Requests and their parameters are audit records and cannot be edited directly.
- Packaging UOMs do not create different Item identities.
- Existing approved Items are returned immediately; no unnecessary request is created.
- Repeating the same pending request returns the existing request instead of creating a duplicate.
- After a transaction-originated request is approved, return to the transaction and use **Resolve / Request Item** again with the same parameters. The now-approved Item will be inserted immediately.
