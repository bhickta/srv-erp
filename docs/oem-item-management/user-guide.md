# OEM Catalog guide

Choose Customer, Company, and the authorized physical Brand. Search the base-product portfolio and configure the approved selectors. Decimal dimensions and printed wording use their appropriate typed controls. Packaging shows the fixed relationship to stock quantity.

Review the physical specification. An exact released match reuses its Item. A missing match creates an approval request without creating stock. Save a private configuration draft explicitly if choices are incomplete; resume it from My configuration drafts.

On a draft Sales Order, Configure OEM Item adds a concrete row for an existing match or a separate pending intent line. Use the line cards to edit quantity, delivery date, warehouse, estimate, and notes, then Save pending SO. Estimates do not enter official ERPNext totals. The order has a normal SO ID and remains a draft. A rejected or abandoned intended line must be corrected or explicitly withdrawn with a reason before submission.

A different authorized approver reviews the request under Approvals. Physical release does not replace ordinary commercial/customer-history approval, a selling price, or a BOM.

Reopen the draft and use Refresh approval / Apply. Confirm ordinary item details/pricing and explicitly save. Approval never saves an order in the background. Submitted/stale orders or a changed customer/company/brand cannot be overwritten by an old request.

For labels, use Configure OEM Item in Package Barcode Generator, choose a fixed package and whole package count, review stock quantity, then Generate. Retrying a lost response with the same command returns the same completed batch. Download uses the existing protected Excel route. Managed Force Barcode Only stock flows support one fixed UOM per Item; unsafe mixed-UOM managed cases are blocked.

If a configuration is stale, reload current rules while retaining your choices. If physical stock drift is reported, ask the catalogue manager to review the binding. Do not change an Item's meaning or conversion factor to clear the error.
