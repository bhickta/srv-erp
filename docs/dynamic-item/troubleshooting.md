# Dynamic Item Approval troubleshooting

Start by opening **Masters > Dynamic Item Requests** and checking whether a request already exists for the same parameters.

## The Resolve / Request Item button is not visible

Check all of the following:

- the document is new or Draft;
- you can create or edit that document;
- **Enable Dynamic Item Requests** is on;
- you have one of the configured Requester Roles;
- the document's Item table is enabled under **Masters Settings > Desk Item Grids**;
- the table is editable and its child rows have an editable `item_code` Link to Item;
- the browser has been refreshed after deployment or settings changes.

An administrator can select **Refresh Profiles and Item Grids** to discover eligible grids.

## Request Variant is not visible on an Item

The Item must be an Item template with:

- **Has Variants** enabled;
- **Variant Based On** set to `Item Attribute`;
- an enabled Dynamic Variant Profile;
- Dynamic Item Requests enabled for your requester role.

The action appears under **Create > Request Variant**.

## Common messages

| Message or symptom                                                                  | Cause                                                                                    | Resolution                                                                                |
| ----------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| Dynamic Item Requests are disabled in Masters Settings.                             | The administrator has not enabled the feature or has paused it.                          | Ask a Masters administrator to complete rollout checks and enable requests.               |
| User … is not permitted to request dynamic Items.                                   | Your roles do not intersect the configured Requester Roles.                              | Ask an administrator to assign the correct role or update Masters Settings.               |
| No other enabled System User has the configured approver role ….                    | No eligible maker-checker approver exists apart from the requester.                      | Enable/assign a different System User with the Approver Role.                             |
| Dynamic Variant Profile is not configured for ….                                    | The template has no profile.                                                             | Run **Refresh Profiles and Item Grids** or create/review the profile.                     |
| Dynamic Variant Profile is disabled for ….                                          | The template has been intentionally closed to requests.                                  | Ask the Masters owner whether it should be re-enabled.                                    |
| … is not an Item Attribute-based template.                                          | The selected Item is not an eligible variant template.                                   | Select or correctly configure an Item Attribute-based template.                           |
| Item template … is disabled.                                                        | The template is inactive.                                                                | Use an active template or ask the Item owner to review it.                                |
| Missing required variant attributes: ….                                             | A profile parameter marked Required was left blank.                                      | Enter every listed required value.                                                        |
| Attribute … is not allowed by this profile.                                         | The attribute is neither in the profile nor permitted dynamically.                       | Remove it or ask an administrator to add/allow it.                                        |
| New values are not allowed for attribute ….                                         | The profile allows only existing values.                                                 | Select an existing value or request a governed master-data change.                        |
| Brand … is disabled.                                                                | The matching Brand master is disabled.                                                   | Select an active Brand or have the Brand reviewed.                                        |
| Numeric attribute … must be configured on the template profile first.               | A numeric attribute was entered dynamically or is missing template/profile setup.        | Ask an administrator to configure it before requesting.                                   |
| Attribute/number does not follow range or increment.                                | The numeric value violates template settings.                                            | Use a permitted value or have the template rule reviewed.                                 |
| UOM … does not exist.                                                               | The packaging UOM master is missing.                                                     | Create/approve the UOM master first, then retry.                                          |
| Conversion Factor for … must be greater than zero.                                  | Factor is zero, negative, empty, NaN, or infinite.                                       | Enter a finite positive number.                                                           |
| Stock UOM … must have conversion factor 1.                                          | A different factor was supplied for the stock UOM.                                       | Use `1` or omit the stock-UOM row.                                                        |
| UOM … already has conversion factor …; requested factor … is a conflict.            | The Item already contains that UOM with a different factor.                              | Verify the correct factor with the master-data owner; do not submit an overwrite request. |
| UOM … already has a pending packaging request ….                                    | Another pending request covers the same Item/UOM.                                        | Open and complete the linked request instead of duplicating it.                           |
| Matching Item … exists but is disabled.                                             | A matching disabled Item already exists outside the pending flow.                        | Ask a Masters administrator to reactivate or resolve the existing Item.                   |
| Generated Item Code … conflicts with a different Item.                              | Attribute abbreviations produce an Item code already used by another identity.           | Review attribute/Brand abbreviations and naming policy.                                   |
| Pending Dynamic Items cannot be used: ….                                            | A staged Item code was placed in a document before approval.                             | Remove it; after approval use Resolve / Request Item again.                               |
| Dynamic Item approval fields can only be changed through the Masters approval flow. | Someone tried to edit protected Item approval data, attributes, UOMs, or disabled state. | Revert the manual edit and use Approve, Reject, or Cancel Request.                        |
| Dynamic Item Request state can only be changed through approval actions.            | Someone attempted to edit the audit record directly.                                     | Use the Actions buttons. For changed parameters, terminate and resubmit.                  |
| Requesters cannot approve their own Dynamic Item Request.                           | Maker-checker separation blocked self-approval.                                          | Ask a different eligible approver to review it.                                           |
| Bulk variant creation is disabled in Masters Settings.                              | Bulk creation is off by policy.                                                          | Use on-demand request flow. Policy changes require administrator review.                  |
| Bulk variant creation is unavailable while variant approval is enforced.            | Bulk and approval enforcement are mutually exclusive.                                    | Keep approval enforcement and use Resolve / Request Item.                                 |
| Use Resolve / Request Item so the new variant follows Masters approval.             | Quick-entry variant creation was blocked.                                                | Use the transaction grid action or Item template's Request Variant action.                |

## The request was approved but the transaction row is still blank

This is expected. A pending request never inserts its disabled Item into the source transaction, and approval does not silently modify an open document.

1. Return to the Draft transaction.
2. Click **Resolve / Request Item**.
3. Enter the same template and parameters.
4. Click **Resolve / Request**.

The approved Item now resolves immediately and is inserted into the Item table.

## The same request keeps returning

The system intentionally reuses an active request with the same canonical identity or exact packaging signature. Open the linked request and complete, reject, or cancel it.

Case differences and attribute order do not create separate identities.

## An approver did not receive an assignment

The request is still valid even if assignment creation or notification failed.

- Open **Masters > Pending Item Requests**.
- Confirm the user is enabled, is a System User, and has the configured Approver Role.
- Ask an administrator to check the Error Log for **Dynamic Item Approval Assignment Failed**.
- Review email/notification configuration separately from the request workflow.

## A staged Brand, attribute, or value is visible before approval

This is expected for new categorical master data. It is provisionally created so the system can construct and display the staged Item.

Do not rename, delete, or reuse provisional data while the request is pending. Approval adopts it. Rejection/cancellation removes it only when it remains unapproved and unreferenced.

## Rejection did not remove a categorical master

Cleanup deliberately preserves data when it is:

- used by an Item variant;
- adopted by an approved request;
- shared by another pending request;
- referenced by another master or Item.

An administrator should review references before removing it manually. Also check the Error Log for **Dynamic Item Schema Cleanup Failed**.

## Approve, Reject, or Cancel is not visible

- **Approve**: visible only to an eligible approver who is not the requester, and only while Pending Approval.
- **Reject**: visible only to an eligible approver while Pending Approval.
- **Cancel Request**: visible to the requester while Pending Approval.

Refresh the request form after a role or status change. Terminal requests have no further action buttons.

## A profile cannot be saved

Common administrator causes are:

- duplicate attributes in the profile;
- a numeric attribute not attached to the template;
- a Required attribute not attached to the template;
- existing variants missing an attribute that is being changed to Required;
- an Item that is not an Item Attribute-based template.

Correct the template and existing variant data before tightening the profile.

## A Masters Settings grid row cannot be saved

Confirm:

- Document Type exists;
- Table Field is an actual Table field;
- Child DocType matches the Table field's options;
- the child DocType contains an `item_code` Link to Item;
- the same Document Type and Table Field pair is not already listed.

## Escalation information to collect

When contacting a Masters administrator, provide:

- Dynamic Item Request ID, if created;
- Item template;
- exact attributes and packaging UOMs entered;
- source DocType and document name;
- full validation message;
- requester and intended approver users;
- whether the issue is reproducible with another template.

Do not include passwords, API keys, or unrelated customer data in screenshots or support tickets.
