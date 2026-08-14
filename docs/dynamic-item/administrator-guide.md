# Dynamic Item Approval administrator guide

This guide is for System Managers and Masters administrators responsible for Item governance.

## Purpose of the configuration

Dynamic Item Approval is designed to create only variants that are actually requested. Administrators define:

- who may request and who may approve;
- which Item templates participate;
- which parameters are required and whether new values are allowed;
- which transaction Item tables expose the user action;
- whether direct and bulk variant creation remain blocked.

## Safe defaults after installation or migration

The feature is installed conservatively:

| Setting                               | Initial value          | Reason                                                       |
| ------------------------------------- | ---------------------- | ------------------------------------------------------------ |
| Enable Dynamic Item Requests          | Off                    | Roles, profiles, and grids must be reviewed first.           |
| Enforce Approval for New Variants     | On                     | New variants must follow maker-checker control.              |
| Allow Bulk Variant Creation           | Off                    | Prevents uncontrolled Cartesian-product creation.            |
| Allow New Categorical Attributes      | On                     | Permits controlled on-demand extension through approval.     |
| Use Template Image on Staged Variants | Off                    | Avoids copying template images unless intentionally enabled. |
| Approver Role                         | Masters Item Approver  | Provides a dedicated approval role.                          |
| Requester Roles                       | Masters Item Requester | Provides a dedicated request role.                           |

Existing Items and variants are not changed by rollout.

## Recommended rollout sequence

1. Review Item templates and clean duplicate Item Attribute values.
2. Confirm required UOM masters exist.
3. Assign requester and approver roles to different enabled System Users.
4. Open **Masters > Masters Settings**.
5. Leave **Enable Dynamic Item Requests** off during configuration.
6. Review all settings and enabled Item grids.
7. Select **Refresh Profiles and Item Grids**.
8. Review every Dynamic Variant Profile that users will access.
9. Confirm direct/bulk Item creation policy.
10. Enable **Dynamic Item Requests**.
11. Run the rollout acceptance test at the end of this guide.

## Roles and separation of duties

### Default roles

- **Masters Item Requester**: can use the request flow and read relevant settings, profiles, and requests.
- **Masters Item Approver**: can review requests and can maintain Masters Settings and Dynamic Variant Profiles.
- **System Manager**: has full configuration access and can inspect all requests.

The requester role list and approver role are configurable in Masters Settings. Role names shown in this guide are the defaults.

### User requirements

Before new requests can be submitted, ensure:

- at least one enabled `System User` has a configured requester role;
- at least one different enabled `System User` has the configured approver role;
- the requester and approver use named accounts for traceable audit history.

A requester who also has the approver role still cannot approve their own request.

When changing the Approver Role, assign the new role to users before saving the operational change. Otherwise, request creation fails because no other eligible approver is available.

## Masters Settings reference

Open **Masters > Masters Settings**.

### Dynamic Item Creation

| Setting                               | Effect                                                                                                               | Recommended production value                  |
| ------------------------------------- | -------------------------------------------------------------------------------------------------------------------- | --------------------------------------------- |
| Enable Dynamic Item Requests          | Shows the requester actions and permits new resolve/request operations. Turning it off pauses new requests.          | On after rollout checks.                      |
| Enforce Approval for New Variants     | Blocks direct variant insertion, protects pending Items, and prevents pending Items from being used in transactions. | On.                                           |
| Allow Bulk Variant Creation           | Enables ERPNext bulk variant generation only when approval enforcement is off.                                       | Off for on-demand governance.                 |
| Allow New Categorical Attributes      | Shows **Additional Categorical Attributes** and allows missing non-numeric Item Attributes to be staged.             | On only when approvers govern new attributes. |
| Use Template Image on Staged Variants | Copies the Item template image while constructing the staged variant.                                                | Based on media policy.                        |

**Enforce Approval for New Variants** and **Allow Bulk Variant Creation** cannot both be enabled.

### Roles

| Setting         | Meaning                                                    |
| --------------- | ---------------------------------------------------------- |
| Approver Role   | The single role allowed to approve and reject requests.    |
| Requester Roles | One or more roles allowed to use the resolve/request flow. |

At least one Requester Role and an Approver Role are required before Dynamic Item Requests can be enabled.

### Desk Item Grids

Each enabled row identifies a transaction form on which **Resolve / Request Item** appears.

| Column        | Meaning                                                              |
| ------------- | -------------------------------------------------------------------- |
| Enabled       | Whether the action is active for this grid.                          |
| Document Type | The parent form, such as Sales Order.                                |
| Table Field   | The fieldname of the editable child table.                           |
| Child DocType | The child row type; populated from the selected table and read-only. |

A valid grid must be an editable Table field whose child DocType contains an editable `item_code` Link to Item. The same Document Type and Table Field pair can appear only once.

Disable a grid row when users should no longer request Items from that business process. Removing grid access does not affect existing requests.

## Refreshing profiles and Item grids

Select **Refresh Profiles and Item Grids** on Masters Settings after:

- installing an app that adds transaction Item tables;
- adding or customizing an editable Item child table;
- creating new Item Attribute-based templates;
- completing a migration that introduced the feature.

The refresh:

- creates a Dynamic Variant Profile for every eligible template that does not already have one;
- adds every newly discovered eligible Item grid;
- leaves existing profiles and grid rows intact.

The confirmation reports how many profiles were created and how many grids were added. Review newly added records before exposing them to users.

## Dynamic Variant Profiles

Open **Masters > Dynamic Variant Profiles**. There is at most one profile per Item template.

### Profile fields

| Field              | Meaning                                                                                                                     |
| ------------------ | --------------------------------------------------------------------------------------------------------------------------- |
| Item Template      | An Item Attribute-based variant template governed by this profile. The template must be enabled when users submit requests. |
| Enabled            | Whether users may resolve/request against this template.                                                                    |
| Variant Parameters | The ordered list of attributes shown in the request dialog.                                                                 |
| Required           | Whether the requester must supply this attribute.                                                                           |
| Allow New Values   | Whether a requester may type a new categorical value instead of selecting an existing one.                                  |

### Profile design guidance

- Include only attributes that genuinely determine Item identity.
- Keep packaging, rate, supplier, description, and transaction-specific details out of identity.
- Mark an attribute Required only when every valid future variant must contain it.
- Disable **Allow New Values** for controlled vocabularies.
- Use clear Item Attribute names and maintain consistent abbreviations.
- Disable the profile when the template should no longer accept on-demand requests.

### Profile validations

The system prevents:

- profiles for Items that are not Item Attribute-based templates;
- duplicate Item Attributes in one profile;
- new numeric attributes that are not already configured on the template;
- making an unattached attribute Required;
- making an attribute Required when existing variants of that template do not contain it.

### Numeric attributes

Numeric attributes require prior administrator setup:

1. Configure the numeric Item Attribute.
2. Attach it to the Item template.
3. Set its from-range, to-range, and increment on the template.
4. Add it to the Dynamic Variant Profile.
5. Decide whether it is Required.

Requesters cannot dynamically introduce a numeric attribute.

## Item master fields added for approval

The **Dynamic Item Approval** section on Item records contains read-only audit fields:

| Field                        | Purpose                                                                             |
| ---------------------------- | ----------------------------------------------------------------------------------- |
| Dynamic Item Approval Status | Blank for legacy/non-dynamic Items, Pending Approval for staged Items, or Approved. |
| Dynamic Item Request         | Links the Item to its originating request.                                          |
| Dynamic Item Requested By    | Records the requester.                                                              |
| Dynamic Item Approved By     | Records the approver.                                                               |
| Dynamic Item Approved On     | Records approval time.                                                              |

The system also maintains an internal unique variant signature to prevent duplicate dynamic identities. Users should not alter approval fields through customization or data import.

## Brand and categorical master governance

When allowed, a request may stage:

- a new categorical Item Attribute;
- a new Item Attribute Value and abbreviation;
- a new Brand when the attribute is Brand;
- the attribute link on the Item template;
- the corresponding profile row.

These master records may become visible while the request is pending because they are needed to construct and review the staged Item. Treat them as provisional:

- do not manually rename, delete, or adopt them while approval is pending;
- do not create spelling variations of an existing Brand or value;
- reject requests that violate master naming standards.

On rejection or cancellation, request-owned artifacts are removed only when no approved request, Item variant, other pending request, or master reference has adopted them.

## Pausing or changing the process

### Pause new requests

Turn off **Enable Dynamic Item Requests**. Request buttons disappear and new requests are blocked. Existing pending requests remain available to approvers for resolution.

### Keep approval enforcement on

Do not turn off **Enforce Approval for New Variants** merely to bypass an operational problem. Doing so weakens direct-creation and transaction guards. Resolve the role, profile, or master-data issue instead.

### Bulk creation exception

Bulk variant creation is mutually exclusive with approval enforcement. Enabling bulk creation represents a governance-policy change, not a routine troubleshooting step. Review the Item proliferation risk and obtain business approval before changing both settings.

## Rollout acceptance test

Perform this test with two named users.

1. As a requester, resolve a combination that already exists. Confirm it is returned immediately.
2. Request a missing combination. Confirm a pending request and disabled staged Item are created.
3. Try to use the staged Item in a Draft transaction. Confirm it is rejected.
4. As the same requester, confirm **Approve** is not available.
5. As a different approver, review and approve the request.
6. Confirm the Item becomes enabled and Approved.
7. As the requester, resolve the same combination again and confirm it is returned immediately.
8. Request a new packaging UOM for that Item and confirm no new Item is staged.
9. Approve the packaging request and confirm the UOM row appears on the existing Item.
10. Submit and reject a request containing a new test categorical value. Confirm the staged Item is deleted and the request audit remains.

## Ongoing administration checklist

Review regularly:

- pending requests older than the agreed service level;
- repeated rejection reasons indicating training or profile problems;
- disabled or departed approver accounts;
- newly created Brands, attributes, and values;
- duplicate spellings and abbreviations;
- Dynamic Variant Profiles after template changes;
- newly discovered Item grids after app installation or customization;
- any attempt to enable bulk creation or disable approval enforcement.
