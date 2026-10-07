# OEM Item Management — implementation contract

Status: PLANNING ONLY. No implementation, site migration, data conversion, or production setting change was performed to prepare this document.
Prepared: 2026-10-07.
Project: bhickta/srv-erp. Base branch: version-15.
Inspected source baseline: a41f98875c8f874819051eed6b01980fe114a1b8.
Recommended module: OEM Catalog, Python package srv_erp.oem_catalog.
Private production evidence: /home/bhickta/development/OEM_PRODUCTION_AUDIT.md. That file must never be committed or uploaded.
This document is an implementation contract, not permission to deploy to production.

## 1. Intended outcome

Let a salesperson or barcode operator find or configure a real product in a few guided steps, with visible defaults, pictures when available, customer/brand context, accurate packaging, and an understandable review screen. Reuse an existing stock Item whenever it represents exactly the same interchangeable stock. Create one new ERPNext Item only when an approved, actually needed specification has no suitable existing Item.

The catalogue contains the company's finite portfolio of base products. It is not the list of every brand/colour/packaging combination. Real customizations remain possible without expanding every theoretical combination.

Confirmed business decisions:

- Two customers share the same Item when the physical stock is interchangeable.
- Branding, stickers, packaging, colour, certification, and design can make stock non-interchangeable.
- Customer identity and commercial preferences alone do not split stock.
- Development must be isolated and production data must remain usable throughout.
- The solution must be configurable, navigable, maintainable, auditable, and production-ready.

Some legitimate new combinations will require new Items. The goal is to avoid unnecessary Items, not to force physically different stock into one code.

Success means the full sequence works: catalogue selection -> contextual configuration -> exact-match reuse or request -> approval -> safe Item binding -> Sales Order or barcode use -> downstream transactions -> support, monitoring, and rollback.

## 2. Non-negotiable working rules for the implementation agent

1. Create, clone, check out, modify, build, and test only under /home/bhickta/development.
2. Treat all of /home/frappe as read-only. Do not run bench commands there, initialize Frappe there, change files or permissions there, or mutate its Git repositories.
3. Never connect a test, migration, development site, worker, or scheduler to the production database, Redis, site configuration, file store, mail, payment, or integrations.
4. Fetch the latest origin/version-15, create a fresh feature branch and an isolated worktree, then pull the base with --ff-only before edits. Preserve existing worktrees and user changes.
5. Commit small, reviewed increments; push a feature branch and open PRs. Do not merge or deploy.
6. Never delete, rename, merge, disable, re-parent, or recalculate existing Items as part of module installation or adoption.
7. Never change existing stock quantities, UOM factors, valuation, Item Prices, submitted documents, BOMs, barcodes, or workflows during adoption.
8. Never call activate_dynamic_item_creation, brand backfill, variant synchronization, or bulk-variant generation to bootstrap this module.
9. Seed synthetic example.com data only on a development/test site. No sample masters on production.
10. Keep the private production audit, credentials, customer names, transaction exports, screenshots containing live data, and backup files out of Git and PRs.
11. If a task requires a business decision or new external authority, finish independent work and record the exact unresolved decision. Do not invent a data migration.
12. Do not declare production readiness when required real-database, browser, concurrency, or non-interference checks have not run.
13. This handoff authorizes implementation and reviewable PRs. Production activation remains an operator-controlled change.

There is no requirement to rewrite Frappe, ERPNext, the existing Masters module, or unrelated srv_erp functionality.

## 3. Evidence-based current architecture

The private audit records measured counts and live settings. Source observations below can be independently reproduced on the stated commit. They describe inspected code and database metadata; an authenticated browser usability session was not performed.

| Existing area | Source entry points | Relevant behavior |
| --- | --- | --- |
| Dynamic requests | srv_erp/masters/dynamic_item/api.py, request_flow.py, staging.py, approval_flow.py | Matches variants by template/attributes; missing combinations stage disabled Items before approval |
| Transaction dialog | srv_erp/public/js/dynamic_item_request.js | Template dialog, sometimes a second Brand dialog, then attribute controls and editable UOM table |
| Builder page | srv_erp/masters/page/variant_builder/variant_builder.js | Separate template/Brand form; some brand/group defaults, but limited customer/source context |
| Brand auto-creation | srv_erp/item/variant_auto_creation.py | Brand and Item Attribute hooks can trigger missing-variant generation |
| Coverage creation | srv_erp/srv_erp/report/variant_coverage/variant_coverage.py | Existing theoretical-coverage/bulk creation path; never use for new catalogue bootstrap |
| Brand rule publication | srv_erp/masters/dynamic_item/brand_rule_sync.py | Can add attributes to existing template schemas; audits existing variants |
| Existing default/backfill tools | brand_default_backfill.py, brand_value_sync.py | Explicit operations can add/change existing variant attributes |
| Item synchronization | srv_erp/item/variant_field_sync.py | Existing variants inherit controlled fields from templates |
| Item identity editing | srv_erp/item/variant_attribute_edit.py, hooks.py | Item class override allows certain existing variant attribute edits |
| Pricing | srv_erp/item/variant_price_sync.py | Existing template prices synchronize to variants; standalone new Items will not inherit this automatically |
| Sales Order item lookup | srv_erp/selling/sales_order.py, public/js/sales_order.js | Brand-filtered lookup reads Item Variant Attribute, not just Item.brand |
| Sales Order defaults | public/js/sales_order.js, selling/sales_order_attributes.py | branding_type, color, marketed_by exist at parent and child levels and are copied independently of variant resolution |
| Sales Order UOM | srv_erp/selling/sales_order_uom.py | Traverses group ancestors and currently picks the first configured ancestor from root toward leaf |
| Sales Order commercial approval | srv_erp/selling/sales_order_item_approval.py | Customer purchase-history approval is distinct from physical Item/specification release |
| Barcode generation | srv_erp/package_barcode/api.py and service.py | Generates Package Barcode Batch and Package Barcode for a concrete Item/UOM |
| Barcode generator page | srv_erp/srv_erp/page/package_barcode_generator/package_barcode_generator.js | Item link, UOM select, count, preview; not the same guided configurator |
| Barcode scanning | srv_erp/package_barcode/service.py | Stock Reconciliation converts package UOM to stock quantity; other flows count packages under current rules |
| Installation/migration | srv_erp/install.py, masters/setup.py, patches.txt | Existing hooks and patches can synchronize masters and grant roles; module isolation alone does not make whole-app migration inert |

Important gaps to solve:

- Customer -> many Brand associations must be explicit; transaction history is a suggestion source, not ownership proof.
- Catalogue identity, configurable manufacturing specification, and transaction preferences need separate models.
- Existing metadata may be missing or contradictory. A missing value is unknown, not a wildcard match.
- Current transaction customization fields can disagree with a physical Item. New managed rows need a validated physical snapshot.
- Packaging means both an accounting UOM and a physical package/artwork specification. Those meanings cannot be treated as one field.
- Existing generic request grid discovery can attach to newly introduced OEM child tables if they look like transaction grids. Avoid child fields named item_code unless actually needed; add an explicit exclusion only if proven necessary.
- Existing Item/Item Price class overrides remain in effect. New adapters must test against those overrides, not replace them.

## 4. Decision: independent module in the existing app

Implement a bounded OEM Catalog module inside srv_erp. It has its own catalogue, configuration rules, specifications, requests, bindings, workspace, guided UI, tests, and operator commands. ERPNext remains the inventory, pricing, manufacturing, accounting, and transaction system.

New materialized stock Items are ordinary standalone ERPNext Items: has_variants=0, variant_of empty. The OEM module owns the specification relationship in a separate binding table. Existing variant Items may be adopted by read-only binding without conversion to standalone Items.

Why this is the chosen first delivery:

- Reusing ERPNext template/variant as the primary new identity mechanism would retain broad template synchronization and attribute-schema coupling.
- A UI-only change would leave customer context, stock identity, defaults, and item proliferation insufficiently governed.
- One generic Item plus order notes would lose reliable stock segregation for branded, printed, coloured, designed, or certified products.
- A separate Frappe app would add deployment/dependency lifecycle work before the same adapters and data protections are solved.
- A microservice or a separate inventory ledger would introduce distributed consistency with no demonstrated benefit here.

The module boundary makes a later extraction to its own Frappe app possible. Do not promise installation independent of srv_erp in release one. Do not introduce ERPNext logic into the Frappe framework.

## 5. Domain model and terminology

~~~text
Company portfolio
  OEM Product (base product, stable catalogue code, image, category)
    OEM Product Revision (published schema and manufacturing/Item blueprint)
      OEM Specification (immutable, complete physical identity)
        OEM Item Binding -> existing or newly materialized ERPNext Item

Customer <-> OEM Customer Brand <-> Brand
  contextual defaults, favourites, customer reference numbers
  do not become stock identity unless printed/physically meaningful

Draft configuration / request
  does not create an ERPNext Item
  exact released match -> reuse
  missing match -> request -> approval -> bind/create one Item

ERPNext Item -> Sales Order -> Delivery/Invoice
             -> Package Barcode -> existing stock scan flows
             -> BOM / Work Order only after manufacturing checks
~~~

Definitions:

- Product: one genuinely distinct base portfolio product, e.g. a particular MCB enclosure model. Do not merge dimensional products because names sound similar.
- Product revision: published allowed fields, options, rules, defaults, and safe Item blueprint. A revision is not itself a new physical SKU.
- Specification: all facts that distinguish interchangeable finished stock for that Product.
- Context: customer, company, brand authorization, source transaction, quantities, commercial preferences.
- Binding: audited declaration that an ERPNext Item realizes one exact specification.
- Request: workflow and source intent to release/create or safely extend a specification's allowed transaction UOMs.
- Physical package: artwork, sticker, contents, construction, certification marks, and sellable-unit composition.
- Transaction UOM: how quantity is entered and converted to stock units.
- Asset revision: immutable approved artwork/design/certificate version identified by a stable record and checksum.
- Legacy candidate: existing Item requiring verification before it can be treated as an exact specification match.

## 6. Physical stock identity: exact contract

Default identity inputs are Product stable ID, stock UOM, physical Brand, and the Product's explicitly classified identity attributes:

- Colour/finish.
- Branding method and permanent physical branding.
- Sticker/artwork revision and printed contents when present.
- Package design/artwork, physical composition, and contents where stock is sold/stored as that composition.
- Certification scheme/mark and stock-distinguishing product/design certification revision.
- Engineering design revision and relevant dimensions/material/rating where not already fixed by Product.
- Any other approved attribute for which changing the value makes existing stock unsuitable.

Exclude customer, salesperson, source document, price list, rate, discount, quantity ordered, favourite state, display name, translations, and request ID.

Company is authorization/commercial context, not an automatic identity splitter: ERPNext Items are site-wide and stock is segregated by warehouse/company. Product blueprint must provide valid company-specific defaults before that Item is used in a company. Do not create a second Item merely because the company changes.

Brand is normally physical identity for OEM finished products. An explicit unbranded option uses a defined stable ID, never a blank wildcard. Never infer that two differently branded finished goods can share stock.

Customer identity stays excluded. If the product has customer-specific printed text, artwork, certification marking, or design, include the exact approved physical content/revision in identity instead of the customer name.

Certification nuance: a lot-specific inspection result, serial certificate number, or certificate expiry on a batch belongs in existing batch/quality controls; it need not split the product Item. Product design/marking differences do. The Product revision classifies these explicitly. Do not treat all certificate uploads as interchangeable.

Required identity fields must have a value or an explicit approved not-applicable option. Unknown is never equivalent to not-applicable. Prevent submission when required physical facts are missing.

### 6.1 Canonicalization

Implement as a pure function with no Frappe/database imports:

1. Validate against the published Product revision.
2. Resolve enum/master inputs to stable IDs; labels and abbreviations are never identity.
3. Use a stable ASCII lower_snake_case key per attribute. Do not rename keys after first release.
4. Normalize identity text using Unicode NFC and documented trimming. Preserve case/content for printed text; do not universally lowercase it.
5. Numeric values use Decimal with published precision, unit, range, and step. Reject NaN, infinity, excessive precision, and ambiguous units.
6. Set-valued fields are allowed only when declared; sort/deduplicate stable IDs. Ordered fields preserve declared order.
7. Omit only explicitly non-identity fields. Required identity values remain present even when they represent not-applicable.
8. Include stock_uom stable master ID and immutable identity namespace.
9. Serialize canonical JSON with sorted keys, UTF-8, fixed separators, decimal values as normalized strings.
10. Compute SHA-256 over the canonical bytes. Store both payload and hash.
11. On a hash match compare canonical bytes before reuse. A hash collision is a hard conflict.
12. Product revision number and default/profile revision are captured for audit but excluded from physical hash when the physical payload is unchanged.

Illustrative canonical payload:

~~~json
{
  "identity_namespace": "oem-v1",
  "product": "OEM-P-00042",
  "stock_uom": "Nos",
  "attributes": {
    "brand": "EXAMPLE-BRAND",
    "colour": "colour-ivory",
    "branding_method": "sticker",
    "sticker_revision": "OEM-AR-0017",
    "design_revision": "OEM-AR-0031",
    "certification_mark": "cert-none",
    "physical_pack": "pack-standard-carton"
  }
}
~~~

Attribute roles and physical meaning cannot be changed on a published revision once it has released specifications. An identity-breaking change needs a separately approved major identity namespace and explicit equivalence/adoption review. Never rehash or remap existing bindings on publish. Ordinary default or label changes do not create Items.

### 6.2 Worked acceptance examples

| Change | Identity result |
| --- | --- |
| Customer A and B order the same complete physical specification | Same Item; separate customer aliases/access |
| Sales discount changes | Same Item |
| Enter quantity in Nos instead of Box, same product and package semantics | Same Item, valid fixed UOM conversion |
| Sticker file replaced with a different approved printed design | Different specification and normally different Item |
| Option label changes from IV to Ivory, stable option ID unchanged | Same Item |
| Product defaults change, historical specification unchanged | Existing Item unchanged |
| New item only differs in certification document number for one batch | Batch/quality metadata if approved classification says so |
| Finished pack contains a different physical assortment | Different specification |
| Packaging quantity changes but unpacked stock remains interchangeable | Same Item only if transaction UOMs uniquely represent fixed factors |
| Missing colour on a legacy Item | Conflict/verification; do not assume current default |
| Same configuration requested simultaneously by two users | One Specification, one active request, one bound stock Item |
| Rejected configuration requested later | New audited request attempt; no staged Item |

## 7. Data schema: implement these models, not ad hoc custom fields

Use an OEM Catalog module entry in modules.txt and a real srv_erp/oem_catalog/__init__.py. DocType controllers are thin delegators. Field names below are the contract; routine Frappe owner/modified metadata is implicit.

Do not add fields to Item for catalogue identity in release one. Bind externally. Only the transaction and barcode snapshot additions explicitly described later are needed.

### 7.1 Core master records

| DocType | Fields and constraints |
| --- | --- |
| OEM Catalog Settings (Single) | mode: Off/Read Only/Pilot/Active, allow_create_items=0, enable_sales_order_picker=0, enable_barcode_picker=0, default_new_item_series=OEM-STK-.#######, allow_self_approval=0, require_customer_brand=1, max_barcode_batch_size=500, search_page_size=30, max_config_attributes=64, max_option_values=500, max_rule_count=200, configuration_payload_limit_kb=128, notification_retry_limit=5; child pilot roles/users/products/companies; roles mapping; branding/colour mapping; adapter settings |
| OEM Product | immutable catalogue_code unique, display_name, item_group Link, image File reference, description, lifecycle Draft/Active/Retired, optional legacy_template Link Item, current_revision Link OEM Product Revision, search_terms; no Item creation in save hooks |
| OEM Product Revision | product Link, revision Integer, state Draft/Published/Retired, identity_namespace, stock_uom Link UOM, attribute_definitions child table, constraint_rules child table, item_blueprint_json validated allowlist, company_defaults child table, packaging choices, publication_hash, published_by/on; unique product+revision |
| OEM Option Set | immutable code unique, label, values child table; published/referenced option IDs immutable, retirement instead of delete |
| OEM Option Value (child) | immutable value_code unique within parent, label, description, image, sort_order, retired; identity stores parent code + value_code |
| OEM Asset | code unique, kind Sticker/Artwork/Design/Certification, label, permitted_brand optional, lifecycle, current_revision; internal uploads only |
| OEM Asset Revision | asset Link, revision Integer, state Draft/Approved/Retired, private File Link, content_sha256, physical_reference, optional certification_scheme, valid_from/until, approved_by/on; unique asset+revision; approved file bytes immutable |
| OEM Customer Brand | customer Link, brand Link, relationship_label Owner/Distributor/Authorized Buyer/Other, enabled, valid_from/until, default_for_customer, proof_reference optional, approved_by/on; unique customer+brand; no assumption of sole ownership |
| OEM Default Profile | stable profile_code, revision Integer, state Draft/Published/Retired, is_current revision pointer flag, immutable publication_hash, company optional, customer optional, brand optional, product optional, item_group optional, priority Integer, valid_from/until, defaults child table; unique profile_code+revision; published values immutable; clone to a new revision and switch is_current atomically |

Every customer-brand record is permission checked against both linked masters. Brand association creation never saves Brand itself; Brand save hooks can create old variants. An administrator manages new Brand masters through the existing process until a separate safe Brand provisioning task is approved.

### 7.2 Definition child tables

OEM Attribute Definition:

- attribute_key, label, description, data_type Enum/Decimal/Text/Boolean/AssetRevision/MasterLink.
- role Identity/Transaction/Informational.
- group_label, sort_order, required, read_only_policy, hidden_if_not_applicable.
- option_set Link for Enum, approved asset kind for AssetRevision, fixed allowed_master_type for MasterLink.
- decimal_unit, decimal_precision, min_value, max_value, increment.
- max_text_length, allowed_pattern_identifier (predefined safe validators, no arbitrary regex from users).
- default_value_json, default_locked, explicit_na_value.
- stable identity meaning is enforced across revisions.

OEM Constraint Rule:

- rule_code unique within revision, rule_json, user_message, sort_order, enabled.
- Bounded declarative DSL described in section 9; never Python, JavaScript, SQL, or templating code.

OEM Default Value:

- attribute_key, value_json, locked, explanation.
- Values typed/validated against applicable schema at resolution, not blindly applied.

OEM Product Company Default:

- company Link, default_warehouse optional, income_account, expense_account, cost_center, item_tax_template optional, selling_price_list optional, default_sales_uom optional.
- Validate account/company, warehouse/company, currency/UOM, and enabled state on publish and use.
- Blueprint may include ERPNext supported tax/HSN fields only if present and approved in the actual site metadata.
- Do not overwrite company account defaults on existing Items.

OEM Product Packaging Choice:

- code, label, transaction_uom Link, conversion_factor Decimal string, optional physical_pack_value, optional asset_revision, default_for_sales, default_for_barcode, enabled.
- Physical composition/artwork participates in Specification only when identity-classified.
- No two choices on the same stock Item may use the same UOM with different factors.

### 7.3 Operational records

| DocType | Required fields and invariants |
| --- | --- |
| OEM Specification | identity_hash unique, canonical_json immutable, product Link, product_revision Link, identity_namespace, summary, identity_values child, release_state Unreleased/Released/Retired; customer/price/source never stored as identity; canonical fields immutable from insert |
| OEM Specification Value (child) | attribute_key, typed_value_json, display_label_snapshot; no stock Item link |
| OEM Item Binding | specification Link unique, stock_item Link Item unique, ownership Module Created/Legacy Adopted, binding_state Active/Quarantined/Retired, expected_stock_fingerprint, created_from_request, bound_by/on, legacy_evidence_json; never change stock_item on a released binding with usage |
| OEM Configuration Draft | draft_owner Link User, context_json, product_revision, values_json, value_provenance_json, configuration_hash, last_validated_on, expires_on; private to owner/admin; saves do not create Specification or Item |
| OEM Configuration Request | kind Release Specification/Add Transaction UOM, specification Link, submitted_payload_json, configuration_snapshot_json, proposed_uoms_json, payload_hash, active_key nullable unique, status Pending/Approved/Rejected/Cancelled, requested_by/on, approved_by/on, reason, expected_configuration_token, decision_snapshot_json, optional binding; immutable submitted content/context/provenance after submission; decision fields updated only by transition commands |
| OEM Request Source | request Link, actor Link User, source_adapter sales_order/barcode/standalone, source_doctype optional, source_document optional, source_field optional, child_row_name optional, row_intent_id, document_modified_token optional, customer/company/brand context_json, result_state Pending/Ready/Applied/Stale/Abandoned; unique request+actor+row_intent_id |
| OEM Command Receipt | command_key unique (SHA-256 of site+actor+operation+UUID), actor, operation, payload_hash, state Processing/Completed, result_json, created_on; Processing exists only inside an uncommitted command transaction, every committed receipt is Completed; no receipt for rolled-back mutation |
| OEM Customer Item Alias | customer Link, specification Link, customer_item_code, display_name optional, favourite=0, last_used_on optional; unique customer+specification and optional unique customer+customer_item_code when nonempty |
| OEM Barcode Intent | command_key unique, specification, binding, package_choice_snapshot_json, conversion_factor_snapshot, customer/company optional, requested_count, barcode_batch Link Package Barcode Batch, status Completed; active operational output must correspond to completed old batch |
| OEM Import Review | kind Product Bootstrap/Legacy Mapping, source_scope_json, plan_hash, status Previewed/Approved/Applied/Failed, reviewed_by/on, source_baseline, summary_json, rows child; import never runs automatically |
| OEM Import Review Row (child) | source_record, target_product, target_specification optional, proposed_json, source_fingerprint, status Candidate/Conflict/Skipped/Approved/Applied/Failed, reason; avoid field named item_code to prevent old grid auto-discovery |
| OEM Audit Event | actor, occurred_on, operation, entity_type/name, correlation_id, before_hash, after_hash, redacted_details_json; append-only, no update/delete for ordinary users |
| OEM Outbox Event | event_key unique, kind Notify Request/Notify Decision, payload_json limited to IDs, state Pending/Sent/Failed, attempts, next_attempt_on, last_error_code; notification delivery after commit, never part of inventory consistency |

Operational child records have no autonomous create/write permissions. Direct REST insert/update to Specifications, Requests, Bindings, Receipts, Audit Events, and Outbox is denied except authorized internal commands. For masters, server validators protect publication and immutable fields even through imports.

### 7.4 Database constraints and indexes

Create deterministic named indexes in a post-model-sync patch, limited to new OEM tables:

- Unique Product.catalogue_code; OptionSet.code; Asset.code.
- Unique ProductRevision(product, revision); AssetRevision(asset, revision).
- Unique DefaultProfile(profile_code, revision). Publication locks a profile series and selects one is_current Published revision; prior revisions remain immutable historical snapshots.
- Unique Specification.identity_hash.
- Unique Binding.specification; unique Binding.stock_item.
- Unique CustomerBrand(customer, brand).
- Unique Request.active_key: NULL for terminal requests, never empty string.
- Unique RequestSource(request, actor, row_intent_id).
- Unique Receipt.command_key; Outbox.event_key; BarcodeIntent.command_key.
- Unique CustomerAlias(customer, specification). Handle optional customer_item_code with nullable normalized key rather than relying on multiple empty strings.
- Search indexes Product(lifecycle, item_group, catalogue_code), Specification(product, release_state), Binding(binding_state, specification).
- Request(status, requested_on), Request(specification, requested_on), Source(source_doctype, source_document), CustomerBrand(customer, enabled).
- Outbox(state, next_attempt_on), Draft(draft_owner, modified), Alias(customer, last_used_on).

If Frappe field-level unique configuration supplies a single-column index, reuse it; do not create redundant indexes. Composite constraints use frappe.db.add_unique or a named equivalent verified against the pinned runtime. Patches are idempotent and inspect existing indexes before adding.

Use MariaDB constraints for uniqueness; Redis locks alone are not a correctness guarantee. Do not add global indexes to the legacy Item, ledger, or barcode tables without separate measured justification and review.

## 8. Permissions and ownership

Create role definitions without granting them to existing users. Assign pilots explicitly through an operator action:

| Role | Capability |
| --- | --- |
| OEM Catalog User | Search permitted products, configure, create own drafts, submit requests, inspect own source requests |
| OEM Catalog Approver | Review within permitted company/brand/product scope, approve/reject; no self approval by default |
| OEM Catalog Manager | Edit/publish catalogue/rules/options/assets, manage associations, review adoption, inspect audit; does not bypass maker-checker automatically |
| Existing ERPNext roles | Still govern Item, Sales Order, stock, barcode, manufacturing, price, and account access |

Rules:

- Every endpoint requires an authenticated session and checks role plus contextual document/master permission.
- A role alone never grants access to all customers/companies. Respect existing User Permissions and Sales Person mapping.
- Search pagination, suggestions, history, image/File access, request status, previews, and exports all enforce visibility.
- Do not expose an inaccessible matching Item name, pending request, stock quantity, price, or customer's artwork.
- When a physical match exists but cannot be used in this context, return a scoped unavailable/conflict result; do not create another identical Item.
- Maker-checker compares requested_by to acting approver. If self approval is explicitly enabled later, require a manager-only setting, audit configuration change, and record the exception in the decision.
- For an already approved Specification, another authorized customer can use the same Item after association verification; no physical reapproval is required merely for new customer access.
- Pricing and customer purchase-history approval remain separate.
- Direct data import or db_set in application code must not bypass state transitions.

ERPNext Item creation may use a tightly scoped server privilege only inside ItemMaterializer after authorization, ownership, complete schema validation, and permitted company defaults are established. Do not grant Item creation to every salesperson. Never carry ignore_permissions into search or blanket state mutation. Verify all generated fields and call normal Item validators. Document this capability in a security ADR and test rejection as a normal user.

## 9. Configurable defaults and constraints

Default precedence from lowest to highest:

1. Product revision defaults.
2. Published company defaults.
3. Published Brand defaults.
4. Brand + Item Group defaults, most specific allowed group wins.
5. Brand + Product defaults.
6. Customer + Brand defaults.
7. Customer + Brand + Product defaults.
8. Explicit source-row/parent context values.
9. Values deliberately changed by the user in the current configuration.

Customer-approved previous-order configurations are explicit suggestions: selecting Repeat or Copy introduces their values at user-input precedence. Do not silently treat history as the master default.

At the same scope and specificity, higher configured priority wins; an equal-priority conflicting profile is a configuration error. Publication rejects duplicate scope/priority overlaps when determinable; runtime resolution rejects unresolved ties. Define dates in site timezone and evaluate at the transaction/configuration effective date.

Each resolved value returns value, source_type, source_record, source_revision, locked, and explanation. UI displays provenance such as From Brand defaults or You changed this.

Constraints are never overridden by default precedence:

- Allowed values are intersected across applicable policies.
- Locked defaults must agree or configuration is invalid.
- Existing explicit user values survive a context reload if still allowed; invalid ones are highlighted, not silently discarded.
- Blank differs from reset-to-default and explicit not-applicable.
- Parent brand_filter/branding_type/color/marketed_by values are contextual inputs, subject to mappings and physical classification.
- No published profile falls back to arbitrary legacy values without a visible, administrator-reviewed rule.

Bounded rule DSL:

~~~json
{
  "when": {
    "all": [
      {"field": "branding_method", "op": "eq", "value": "sticker"}
    ]
  },
  "require": ["sticker_revision"],
  "allowed": {"colour": ["colour-white", "colour-ivory"]},
  "message": "Choose an approved sticker for this brand."
}
~~~

Supported operators: eq, ne, in, not_in, exists, gt, gte, lt, lte; boolean groups all/any/not. No expressions, eval, exec, custom JavaScript, network URL fetches, SQL fragments, or arbitrary user regex. Validate referenced keys/types, cap nesting at 4 and operations at 200, detect impossible/cyclic dependencies at publish. Backend is authoritative; UI receives a safe display form.

An administrator editor supports adding attributes, options, default profiles, and rules with previews using synthetic examples. Ordinary sales users cannot add global option values from a transaction. An exceptional custom design can use an approved Asset Revision rather than a freely typed new master value.

## 10. Packaging, UOM, and barcode safety

ERPNext can transact one Item in several UOMs while maintaining one stock UOM. A packaging presentation difference does not automatically require another stock Item. A physical package difference may.

Contracts:

- Stock UOM is fixed on a released specification.
- Every Item/UOM pair has one positive, fixed conversion factor.
- Reject zero, negative, NaN, infinity, unit mismatch, and fractional counts for whole-number UOMs.
- Show both package quantity and resulting stock quantity everywhere quantities are chosen.
- A batch count is number of labels/packages, not stock units.
- For stock UOM Nos and Box factor 12, generating 5 Box labels previews 5 packages representing 60 Nos.
- If the same Item needs boxes of 12 and 24, never rewrite Box from 12 to 24. Use two approved distinct existing/new UOM master names, or a physically distinct Item when justified.
- New UOM masters require administrator approval through a separate governed action; do not create global UOM records inside configuration.
- If an adopted Item lacks a needed UOM, return Add Transaction UOM request or an explicit conflict. Never append a UOM during mapping.
- Add Transaction UOM approval can append a new, previously absent Item/UOM pair under explicit authorization; it never changes an existing pair.
- Overlapping UOM requests serialize on the target Item. If a pair was added meanwhile with the same factor, reuse it; a different factor is a conflict. Do not allow two pending proposals to overwrite one another.
- Existing barcode UOM conversions are used at scan time. Freeze every existing factor on adopted Items because previous barcodes may rely on it.
- New module-created factors are also immutable after release. Changing a factor is a new approved package/UOM path.
- Barcode intent captures the factor and package revision used at generation. This is audit metadata, not a replacement for the current scanner.

Do not silently change existing scanning behavior. Preserve the current counting rules for legacy paths and verify the full stock transaction chain for OEM Items.

Release-one OEM adapters must detect a Force Barcode Only transaction containing mixed UOMs for one Item, or row grouping that cannot unambiguously match packages to item/UOM. Block only that managed case with an explanation until a separately specified adapter can handle it correctly. Test a supported fixed-UOM transaction end to end. Do not claim mixed-UOM support from barcode-generation success alone.

Optional later enhancement: a reviewed mixed-UOM reconciliation algorithm can group by Item+UOM and sum normalized stock quantities. It needs a dedicated ADR, new tests for all scan consumers, and its own rollout. It is not part of a quiet global refactor.

## 11. Item materialization and binding

### 11.1 New Item allowlist

Create through ERPNext's normal Item controller, including the srv_erp override already registered. Populate only approved fields:

- item_code using the configured reserved naming series; stable opaque identifier such as OEM-STK-0000001.
- item_name and description from a deterministic, escaped, length-limited summary.
- item_group, stock_uom, is_stock_item=1, has_variants=0, variant_of empty.
- disabled=0 only inside successful approval transaction.
- Brand if physical Brand is present; do not create Item Variant Attribute rows for standalone Items.
- image as an approved accessible File reference if available.
- UOM conversion rows with stock UOM factor 1 plus approved fixed alternatives.
- existing package_barcode_qty_entry_rule from explicit blueprint, otherwise current default.
- selected Item defaults, company defaults, tax/accounting fields supported by actual metadata.
- manufacturing/purchase/sales flags explicitly published and validated.

Never copy an entire template with as_dict. Exclude opening_stock, valuation_rate, standard_rate, last_purchase_rate, current stock quantities, barcode rows, Item customer details, variant attributes, existing dynamic_item_* fields, unrelated child records, and default_bom unless separately verified.

No Stock Entry, opening stock, or Item Price is created by specification approval. Do not create free or zero-price commercial transactions as a fallback.

### 11.2 Legacy adoption

1. An existing Item is a candidate, not an automatic match.
2. Match by verified Product mapping and complete physical metadata, never Item name/code substrings.
3. Compare Brand from Item.brand and variant attribute; disagreements are conflicts.
4. Verify stock UOM, UOM factors, colour, artwork/sticker/design/certification, physical packaging, disabled state, template/variant state, and supported company defaults.
5. Missing physical metadata needs evidence and manager decision recorded in the new import review. Do not fill legacy attribute rows with today's default.
6. A binding can represent verified physical facts in OEM records without writing those facts back to the Item.
7. If two existing Items represent the same physical spec, show a duplicate group; reviewer chooses one eligible canonical binding based on stock/work-in-progress/commercial dependencies. Do not merge Items or move stock.
8. Preserve other duplicate Items and show them in an authorized legacy reference panel. Existing transactions continue to use their original codes.
9. If a second equivalent Item still has usable stock, choose a documented operational fulfillment policy before pilot: operators may use its unchanged legacy path, or a later separately authorized stock consolidation process. Release one cannot silently substitute a different Item on old orders.
10. Binding stores expected_stock_fingerprint for protected physical/UOM fields. On mismatch, quarantine the binding, stop new configurator use, and surface a repair review. Do not rewrite the legacy Item.
11. Module-created Items get server guards against physical/UOM identity edits. Adopted legacy Items initially use detection/quarantine, not blanket new validation that can disrupt old workflows.
12. Adoption creates OEM-only metadata. It does not make unknown legacy stock certified or approved.

Read-only preview/search detects fingerprint drift and returns ITEM_DRIFT without persisting quarantine or audit. A dedicated authorized integrity command or reconciliation job may persist quarantine in OEM-only metadata; it never edits the source Item. Applying/approving/generating rechecks drift inside the command transaction and blocks stale use even before a scheduled quarantine is recorded.

### 11.3 Pricing and manufacturing completeness

Standalone OEM Items will not receive the existing template-variant price cascade. Use ERPNext's normal price resolution and customer pricing rules. An optional explicit price-provisioning command creates reviewed Item Prices for new Items using approved UOM/currency/date/customer dimensions; it does not adopt or change legacy managed prices. Provide a setup dashboard identifying missing prices and defaults before pilot. No valid price means a visible missing-price state, not a fabricated zero rate.

Before manufacturing a new OEM Item, verify BOM, operations, quality plan, design, certification applicability, and manufacturing permissions. Release one can use existing ERPNext BOM creation with the new stock Item. Do not set a template BOM blindly or promise inheritance to standalone Items. A generated OEM BOM is a separately approved, tested adapter if required.

Define readiness dimensions separately: Physical Release, Sales Readiness, Barcode Readiness, Manufacturing Readiness. An approved Item may be suitable for barcode generation but lack a selling price or a BOM. Explain which action is unavailable and why.

## 12. Requests, states, concurrency, and idempotency

Specification physical content is immutable. Release state and request lifecycle are independent: a rejected attempt does not mutate physical content or imply that an Item exists.

Request transitions:

~~~text
submit -> Pending
Pending -> Approved (same transaction as Item binding/materialization or UOM addition)
Pending -> Rejected (reason required)
Pending -> Cancelled (owner/authorized manager, reason)
terminal -> immutable
resubmit -> new request attempt against same immutable specification
~~~

Draft configurations are private, editable, and separate from pending immutable requests. Users correct a rejected configuration by cloning/editing a draft; a physical change creates a new Specification hash.

### 12.1 Submit command

1. Authenticate and check pilot/mode, requester scope, source access, customer-brand association.
2. Parse a strictly typed API DTO; reject unknown keys and oversized payloads.
3. Resolve and validate current Product/profile/asset revisions and the configuration token.
4. Build canonical identity server-side; never trust client hash, item_code, defaults, requester, or result.
5. Begin the normal Frappe request transaction. No manual commit.
6. Reserve/load Command Receipt for actor+operation+idempotency UUID with unique constraint. Insert Processing inside this transaction; a duplicate insertion uses a savepoint and then locks/loads the existing committed Completed receipt. Same key + different payload -> IDEMPOTENCY_CONFLICT; same key + same payload -> replay the authorized recorded result. Processing is never committed and has no detached lease to recover.
7. Get/create Specification by unique hash; on insertion race catch only the duplicate-key condition within a savepoint, then load and compare canonical payload.
8. Lock the Specification row FOR UPDATE.
9. If a valid Active binding exists and is authorized/ready, return EXISTING; no new request or Item.
10. If a missing transaction UOM is requested, create the separate governed UOM request.
11. Otherwise find/create Request with active_key release:<specification hash>, or uom:<binding>:<sorted UOM payload hash>.
12. Duplicate pending request adds an authorized Request Source rather than losing the second origin. Do not expose other sources to the requester.
13. Save immutable context/provenance snapshot and OEM Audit Event, record receipt and notification Outbox Event.
14. Return PENDING with current actor's request/source IDs. Do not insert a disabled Item.
15. Frappe commits on successful completion; notifications run after commit.

Read-only preview must not insert Specification, Request, Receipt, Audit Event, or Draft. Saving a draft is a separate explicit POST.

### 12.2 Approve command

All mutation commands first reserve/replay the actor-scoped Command Receipt as described above; then acquire domain locks below. Finalize it as Completed before successful commit.

1. Authenticate, check approver scope and maker-checker, validate optimistic request version.
2. Lock Specification then Request in a consistent order; for UOM changes also lock target Item after Specification.
3. If already Approved, return recorded binding/result to authorized actor. Rejected/Cancelled -> state conflict.
4. Revalidate assets, eligibility, blueprint, configuration token, Item/binding fingerprints, and packaging.
5. Re-check for an Active binding. Reuse it if another successful approval already bound the exact physical spec.
6. Prefer an explicitly approved existing-item adoption selection if attached; never scan/auto-adopt ambiguous legacy candidates during approval.
7. Otherwise create one new Item via ItemMaterializer and insert unique Binding.
8. Update release_state, terminal request decision snapshot, active_key=NULL, Audit Event, Receipt, and Outbox in the same transaction.
9. Any failure rolls back Item, binding, decision, receipt, and event together. Source remains Pending.
10. No background Item creation and no partial Approved state.

Concurrent first-time requests serialize on the Specification row, not on the entire catalogue or an ERPNext template. The Specification insertion unique constraint solves the first-row race. Item code series collision, unsupported field, missing defaults, or controller validation must roll back normally and yield actionable errors.

Lock order: Command Receipt -> Specification -> Request(s sorted by name) -> Binding -> Item when necessary -> Barcode Intent. Publication/import commands lock their own root series/review consistently and do not acquire a Receipt after domain locks. Do not hold locks while rendering images, sending email, exporting XLSX, or calling external services.

Deadlock/lock timeout: at most two retries of a whole idempotent command, outside its failed transaction, with bounded delay. Never swallow unrelated database/controller exceptions. Unit tests alone do not prove concurrency; run separate real database connections/workers.

### 12.3 Barcode idempotency

For guided generation, reserve a Command Receipt, lock specification/binding, validate count and package choice, then call the existing PackageBarcodeGenerator service within the same transaction and record OEM Barcode Intent.

Same actor+operation+UUID returns the same batch and labels. Same UUID with changed count/UOM/spec -> conflict. If generation fails halfway, rollback legacy batch/labels and new intent/receipt. Naming series gaps after rollback are acceptable; duplicate labels are not.

Do not call the existing unrestricted endpoint from the new UI directly. New endpoint authorizes before using the service.

For module-managed Items, add a narrowly scoped server check in the existing generation API so an alternate call cannot bypass module eligibility or immutable UOM safeguards. Non-managed Items retain existing behavior; broader legacy endpoint permission hardening is a separate review item. Protect downloads of OEM batches through an explicit scoped authorization check or the OEM download endpoint, including existing download routes when they target OEM batches. Do not claim UI-only enforcement.

### 12.4 Cancellation and source lifetime

Cancellation/rejection creates no Item cleanup because no Item was staged. Existing completed bindings/Items are never deleted due to abandoned requests or closed orders.

Approval marks linked sources Ready; it does not save or submit a Sales Order or generate labels automatically. A user-controlled Apply action verifies the document is still editable, context unchanged, row intent still valid, and the row hasn't been removed. Conflicts become Stale. An idempotent Apply never duplicates an order row.

## 13. Guided UI contract

Build one shared configurator used by Sales Order, barcode generation, and the standalone OEM workspace. Use established Frappe Desk controls and design tokens. No separate website, external visual builder, or AI-generated product imagery is needed.

### 13.1 Layout and route

Dedicated page route: /app/oem-catalog. Main views: Find Products, Customer Assortment, My Requests, Approvals (authorized), Catalogue Administration (authorized).

Responsive configuration drawer/dialog:

~~~text
Customer / Company / Brand context             [Change]
Search portfolio...                    Recent | Favourite | All

[Product image or placeholder]  Product name / model
Category / key base specifications / catalogue code

Configure
Colour [swatches + text]       Branding method [choices]
Sticker/design [approved revision cards and preview]
Certification [applicable choices]
Packaging [choice + fixed conversion]
Advanced details [only relevant fields]

Review
Readable physical specification + provenance + changed fields
Existing stock Item / pending request / new request required
Quantity: 5 Box = 60 Nos
Sales / Barcode / Manufacturing readiness

[Use Existing Item] or [Request Approval]        [Save Draft]
~~~

Pictures are optional; absent images use a neutral placeholder and still show useful category/model/specification text. Images must be real approved assets, not invented product photographs.

### 13.2 Find before create

- Open in selected customer's Brand context.
- Show customer-authorized Brands, default only if a single/default association is unambiguous.
- Search Product catalogue names, codes, model specs, category, search terms, and authorized customer aliases.
- Show Recent, Favourite, and Repeat Last Configuration.
- Display exact approved specification matches ahead of new request actions.
- A card includes meaningful name, model, image if any, key physical details, Item code secondary, availability only if user can access stock.
- Never populate the catalogue with the full Cartesian product of options.
- Exact reuse requires complete canonical match. Similar products are clearly marked alternatives and never automatically selected.

### 13.3 Defaults and editing behavior

- Prefill customer/company/brand and relevant source row values in one context call.
- One allowed value can be preselected with visible provenance.
- Attribute choices use swatches/thumbnails/chips only where helpful; always have text labels and keyboard support.
- Only relevant attributes appear; required fields and locked policies are clear.
- Selecting another Brand/Product preserves still-valid user edits and highlights invalidated fields.
- A change in physical fields resets preview/resolve token and readiness. An old asynchronous response cannot overwrite a newer selection.
- Use request sequence IDs or AbortController; disable action while current validation is pending.
- Debounce search at 200 ms; cancel/ignore stale results; preserve field focus.
- Never show success until server response confirms it.
- Distinguish loading, empty result, missing association, no price, no image, configuration conflict, pending approval, disabled legacy match, and lost permission.

### 13.4 Accessibility and state

- Keyboard searchable Product cards, logical tab order, Enter to select, Escape to close.
- Swatches include labels; do not rely on colour alone.
- Dialog focus trap and return focus to invoking row.
- Touch-friendly at 360 px, usable at 1024 and 1440 px.
- User-facing strings via _()/__(); site number/date conventions.
- Screen-reader announcements for load/error/result state.
- Escape all labels and descriptions; preview files through permission-checked Frappe File routes.
- Draft persistence is explicit server-side; no private artwork/customer data in localStorage.
- Unsaved parent forms never get silently saved by the configurator.

### 13.5 Sales Order integration

Add Configure OEM Item on the items grid and on a selected row, for enabled pilot context and docstatus=0 only. Existing item selection remains available.

Context fields: customer, company, brand_filter, branding_type, color, marketed_by, selected row's existing Item and overrides, default warehouse, price_list, currency, delivery date, parent name/modified, child row intent UUID.

The client owns unsaved form context, but the server validates all master IDs and allowed source fields. Saved source names must be authorized; unsaved context is allowed only for users who can create Sales Orders.

On ready Item:

1. Check caller's row intent still corresponds to the target row/document.
2. Set item_code through frappe.model.set_value and await normal ERPNext item-detail events.
3. Apply only the approved physical snapshot/custom metadata.
4. Apply UOM via current Sales Order UOM service; validate the resulting factor.
5. Preserve explicitly entered quantity, rate override, discount, warehouse, delivery date, and row notes unless change requires user reconciliation.
6. Avoid automatic merging of rows with different delivery/pricing/warehouse terms.
7. Mark source Applied only once row is present on a saved document, or keep local application intent and bind it during the user's normal save.
8. If document was submitted or changed meanwhile, show Stale; no automatic mutation.

Add Sales Order Item custom fields (all hidden/read-only initially, module-owned):

- oem_specification Link OEM Specification.
- oem_request_source Link OEM Request Source optional.
- oem_row_intent_id Data unique per document, generated client-side and validated server-side.
- oem_snapshot_json Long Text.
- oem_snapshot_hash Data.

No Item-less placeholder row in the standard items table. Pending sources live in Request Source/draft records and a side panel. The side panel shows the request and Apply when ready. This avoids core ERPNext required-Item validation and old generic Item guards.

Server save and before-submit validation checks only rows with OEM references or Items known to a managed binding. Validate binding, physical snapshot, context/Brand authorization, UOM, fingerprint, and readiness. A user cannot clear OEM fields and bypass the check for a managed Item. Bulk-load bindings for Item codes; use one indexed query per document and return immediately when none are managed.

Physical branding_type/color/marketed_by mapping is explicit. If a value is physically meaningful, it must agree with the specification; override attempts open a new configuration. Informational fields remain order preferences. Colour vs Color master names are not assumed identical; configure an audited mapping by stable keys.

Existing parent-copy scripts can override child fields after insertion. The adapter must prevent that for managed physical fields, or reconcile visibly and reject on server. Minimal narrow change to existing script; no silent global behavior change.

Sales Order commercial/customer-history approval remains untouched and may still be required after OEM approval. Show the two approvals as distinct.

### 13.6 Brand lookup compatibility

Standalone new Items are absent from the existing Brand variant-attribute query. Implement a narrow compatibility change:

- Preserve old results for legacy Items.
- Add Active OEM bindings with canonical physical Brand equal to selected brand.
- Honor Item disabled/has_variants eligibility and user permission in the added branch.
- Deduplicate by Item code; retain stable result shape/order/pagination.
- Apply customer-brand scope in the OEM branch when source customer is supplied; direct transaction server validation is still authoritative.
- validate_sales_order_item_brand uses an OEM binding first for a managed Item; legacy behavior continues otherwise.
- Do not fabricate Item Variant Attribute rows or change variant_of to satisfy the old lookup.
- Permission/ordering defects discovered in legacy lookup should be recorded and addressed only as a focused prerequisite fix when necessary; do not use new raw SQL that leaks records.

### 13.7 Barcode integration

Reuse shared configurator in the barcode generator page through an additive Configure OEM Item action. Keep its existing Item/UOM/count path.

New flow: company/customer/brand context -> choose Product -> reuse/request -> choose approved package -> count -> quantity/label preview -> Generate -> same Batch/Excel download.

Unapproved configurations can save a Barcode source intent but cannot generate. Approval enables a user-clicked Generate action; it never creates labels automatically.

Add Package Barcode Batch custom fields: oem_specification, oem_barcode_intent, oem_package_snapshot_json, oem_package_snapshot_hash. Existing fields and Item links stay unchanged. Store per-label snapshots only if inspection proves batch linkage is insufficient; release one uses immutable batch intent plus frozen factors.

### 13.8 Downstream compatibility

- Delivery Note and Sales Invoice created from OEM Sales Orders retain the concrete Item; canonical identity can be reconstructed from binding even without copied custom fields.
- Stock Entry, Stock Reconciliation, Purchase Receipt, BOM, Work Order, Pick List, and stock reports use standard Item IDs.
- Draft downstream documents with managed Items validate permitted physical/UOM usage at known hooks; avoid a new global wildcard hook.
- Historical submitted documents without OEM references remain processable for returns/cancellation/amendment according to ERPNext rules.
- Do not require customer-brand association on internal stock transfers or purchasing; context policies depend on adapter operation.
- Public customer-facing print formats should show readable Item/spec summary or existing Item name, never implementation hashes or audit IDs.
- Inspect existing order-slip and date-range/stock reports for assumptions about variant_of; add managed Product display as additive behavior only if needed, preserving legacy rows.

## 14. API contracts

Package: srv_erp.oem_catalog.api. All mutations POST only; guest access disabled. Use a consistent v1 envelope.

Read endpoints:

- get_context(source_context) -> allowed Brands, effective config, readiness, association errors.
- search_products(context, query, filters, cursor, limit) -> permission-scoped cards; hard maximum 50.
- get_configuration(product, context, product_revision?) -> typed field definitions, defaults/provenance, package choices, constraint messages, configuration_token.
- preview_configuration(payload) -> canonical summary/hash, EXISTING/PENDING/MISSING/CONFLICT/UNAVAILABLE, differences, readiness, allowed actions; no writes.
- get_my_requests(cursor, filters) -> own sources and authorized outcomes.
- get_request_status(request, source?) -> permission-scoped status, no other customers' sources.
- search_legacy_candidates(product, context, evidence) -> manager-only candidates, explicit missing fields/conflicts.
- get_approvals(cursor, filters) -> approver scope only.

Write endpoints:

- save_draft(payload, expected_modified?, idempotency_key).
- submit_configuration(payload, idempotency_key).
- approve_request(request, expected_modified, reason?, idempotency_key).
- reject_request(request, expected_modified, reason, idempotency_key).
- cancel_request(request, expected_modified, reason, idempotency_key).
- validate_apply(source, document_context, row_intent_id) -> validates and returns canonical application DTO; normal form save persists row.
- generate_barcodes(specification, context, package_choice, count, idempotency_key).
- create_import_preview(scope, kind, idempotency_key).
- approve_import_plan(review, expected_plan_hash, selected_rows, idempotency_key).
- apply_import_plan(review, expected_plan_hash, idempotency_key).
- publish_product_revision / publish_default_profile / approve_asset_revision -> manager commands with typed validation.

Example submission DTO:

~~~json
{
  "api_version": 1,
  "product": "OEM-P-00042",
  "configuration_token": "opaque-server-token",
  "values": {"colour": "colour-ivory", "branding_method": "sticker"},
  "package_choice": "standard-box-12",
  "context": {"customer": "EXAMPLE-CUSTOMER", "company": "EXAMPLE-COMPANY", "brand": "EXAMPLE-BRAND"},
  "source": {"adapter": "sales_order", "doctype": "Sales Order", "field": "items", "document": null, "row_intent_id": "UUID"},
  "idempotency_key": "UUID"
}
~~~

Actual required identity values must be complete; the short example is illustrative, not a valid bypass.

Example result:

~~~json
{
  "api_version": 1,
  "outcome": "PENDING",
  "specification": "OEM-SPEC-000042",
  "request": "OEM-REQ-000075",
  "source": "OEM-SOURCE-000090",
  "item_code": null,
  "actions": ["view_request", "save_draft"],
  "readiness": {"physical": false, "sales": false, "barcode": false, "manufacturing": false},
  "correlation_id": "UUID"
}
~~~

Error codes: INVALID_INPUT, MISSING_ASSOCIATION, FORBIDDEN, CONFIGURATION_CONFLICT, STALE_CONFIGURATION, MISSING_PHYSICAL_VALUE, DISABLED_MATCH, LEGACY_MAPPING_REQUIRED, ITEM_DRIFT, MISSING_PRICE, MISSING_COMPANY_DEFAULTS, UNSUPPORTED_SCAN_UOM, REQUEST_STATE_CONFLICT, IDEMPOTENCY_CONFLICT, RATE_LIMITED, MATERIALIZATION_FAILED.

Return field_errors and localized user_message for validation, correlation_id for diagnosis, and safe retryable flag. Do not return SQL, secrets, raw tracebacks, canonical private artwork of an inaccessible spec, or internal credentials.

Configuration token covers Product/profile/asset publication hashes, permitted context, effective date, and adapter version; generated/validated server-side with authenticated Frappe session. Revalidate on submit and approval. Cache tokens are not authorization.

## 15. Code layout and SOLID boundaries

~~~text
srv_erp/oem_catalog/
  __init__.py
  api.py                         thin exported endpoints, DTO parsing
  errors.py                      typed domain/service errors
  composition.py                 explicit dependency construction
  permissions.py                 scoped authorization helpers
  domain/
    models.py                    immutable dataclasses / value objects
    canonicalization.py          pure physical identity
    rules.py                     bounded rule evaluation
    defaults.py                  deterministic precedence and provenance
    packaging.py                 Decimal/unit/package constraints
    transitions.py               state transition predicates
    fingerprints.py              deterministic protected-field payloads
  application/
    configure.py                 options/preview orchestration
    request_commands.py          submit/reject/cancel
    approve.py                   approval transaction
    drafts.py                    explicit private drafts
    adoption.py                  preview/approve/apply mapping
    source_intents.py             document/row application lifecycle
    barcode_commands.py          authorized idempotent generation
    publication.py               masters publication
    readiness.py                 use-case-specific readiness
  ports/
    repositories.py              small Protocols for relevant aggregates
    authorization.py
    stock_items.py
    prices.py
    source_documents.py
    barcode_generator.py
    events.py
  infrastructure/
    repositories/                focused Frappe persistence adapters
    item_materializer.py         allowlisted ERPNext Item operations
    item_fingerprints.py          batch-loaded Item state projection
    price_resolver.py             existing ERPNext pricing semantics
    barcode_adapter.py           existing generator service adapter
    source_adapters.py            explicit allowlisted source types
    outbox.py                     after-commit delivery + retry
    cache.py                      scoped short-lived config/search caches
    indexes.py                    OEM-only indexes
    import_reader.py              bounded read-only legacy extraction
  hooks/
    item.py                      module-created guard; legacy detection
    sales_order.py               scoped row validation
    downstream.py                explicit known transaction handlers
    barcode.py                   managed-only API policy bridge
  doctype/                       standard Frappe records/controllers
  page/oem_catalog/              thin page bootstrap
  workspace/oem_catalog/
  report/                        scoped readiness/conflict/governance
srv_erp/public/js/oem_catalog/
  api.js
  store.js                       explicit UI state/actions
  context.js
  configurator.js                reusable orchestration
  components/
    product_cards.js
    attribute_controls.js
    asset_preview.js
    packaging_picker.js
    review_panel.js
    request_status.js
  adapters/
    sales_order.js
    barcode_generator.js
  admin/
    schema_editor.js
    defaults_editor.js
    legacy_review.js
srv_erp/public/css/oem_catalog.css
srv_erp/tests/oem_catalog/
  unit/
  integration/
  security/
  migration/
  concurrency/
  fixtures/
docs/oem-item-management/
  IMPLEMENTATION_PLAN.md
  HANDOFF.md
  architecture.md
  api.md
  operator-runbook.md
  user-guide.md
  decisions/
~~~

Rules:

- Domain imports only standard library and internal domain modules.
- Application depends on domain and narrow ports, never concrete JS/Frappe documents.
- Infrastructure may import Frappe/ERPNext/legacy services; domain cannot.
- Controllers and HTTP methods authorize/parse/delegate; no duplicated business logic.
- Explicit constructor dependencies, no service locator in domain, no generic BaseService framework.
- One responsibility per module; aim for roughly 250 lines where useful, without artificial fragmentation.
- No cycles, no legacy dynamic-item imports except reviewed boundary adapters where unavoidable.
- Server is source of truth for identity/default validity; client renders returned schema and revalidates.
- Type public DTOs; use dataclasses/Protocols and Python runtime actually supported by the repo.
- Transactions are owned by application command/Frappe lifecycle, never controllers' on_update commit.
- JS components have explicit destroy/unsubscribe and stale-response handling.
- No global monkey-patches to Frappe grid or Item classes.
- Preserve all currently registered controller overrides.
- Add architecture tests for dependency direction and forbidden legacy write calls. Do not merely test line counts and call that architecture assurance.

Maintain docs with short entry-point maps so a new agent can find commands, state transitions, adapters, and tests without reading a giant service file.

## 16. Modes, feature flags, and non-interference

Mode policy:

| Mode | Read/configure | New requests | Item/UOM writes | Integrations |
| --- | --- | --- | --- | --- |
| Off | No new OEM UI | No | No | Legacy unchanged |
| Read Only | Authorized catalogue/preview | No; draft writes disabled in this mode | No | No application/generation |
| Pilot | Selected users/roles + companies + products | Yes in pilot scope | Only when allow_create_items and approval succeed | Individually enabled |
| Active | Authorized scope | Yes | Governed | Individually enabled |

Feature settings affect new decisions, not existence of already created ordinary ERPNext Items. Switching to Off stops configurator commands and creation; it must not make existing released Items unusable in ERPNext. Managed physical/UOM protection remains for module-created Items, and legitimate existing transactions continue. Separate creation kill switch from integrity validation.

Allow_create_items defaults false even in Pilot. Adoption-only pilots are supported.

No auto-enable on install/migrate. No automatic role grants, product imports, settings rewrites, old request conversion, old Item field changes, or variant backfill. New code hooks first test OEM metadata/table availability during migration and return safely when absent.

Client integration handlers register only when their explicit flags and pilot scope apply. No catalogue scans on every Desk boot. An optional small boot flag can indicate availability; full configuration loads on use.

Off mode with legacy-only transactions adds no Item write, no new query expansion, and at most one cheap cached availability check. Integrity checking of known module-created Items is deliberate and documented; no global wildcard document event.

The old grid request button may coexist during transition. If hidden for a pilot transaction, use a scoped adapter decision; do not remove old buttons globally.

## 17. Data bootstrap and adoption without pollution

Installation creates schemas, pages, role definitions, and disabled settings. It creates zero Products, Specifications, Requests, Bindings, stock Items, Item Prices, or barcodes.

Manual first pilot bootstrap:

1. Select a few real portfolio Products with catalogue owner.
2. Read existing template/base records as source; produce an OEM Import Review preview only.
3. Copy safe Product description/category/image/stock-UOM suggestions into preview rows.
4. Product schemas and identity classifications need human review; existing optional attributes do not prove the required physical model.
5. Review repeated/overlapping base products and decide catalogue identity before publishing.
6. Publish approved Products, typed options, package choices, assets, defaults, and customer-brand associations in OEM-only tables.
7. Generate candidate legacy mapping previews for chosen Products.
8. Review complete physical evidence and stock/commercial readiness; apply only approved OEM metadata rows.
9. For unusable/missing/ambiguous legacy candidates, leave unbound and continue the old path.
10. Do not import every legacy variant into the guided catalogue. Make used/approved configurations discoverable through bindings; preserve all legacy records separately.

Plan fingerprint includes source Item.modified and protected field payload, relevant Product/profile/asset publication hashes, plan scope, and selected rows. Before apply, re-read and compare every approved row. Any changed source becomes Stale/Conflict, not guessed.

Bulk imports use bounded chunks (default 100), resumable per-row state, explicit savepoints, unique constraints, and clear partial results. Plan application writes OEM metadata only. Failure never changes legacy stock/master records. Release/readiness transitions remain application commands.

No cleanup of old dummy/unreferenced Items in this project. A later archival project must inspect every standard/custom link, stock/bin/reservation, submitted and draft document, BOM, manufacturing WIP, barcode, integration, and external reference before proposing anything. The private audit's narrow usage counts are not that proof.

## 18. Isolated development and reproducible environment

Preflight deliverables:

- Record exact current origin/version-15 and source versions/dependency pins.
- Inspect applicable AGENTS.md in each writable project; do not copy Frappe framework instructions into srv_erp unless applicable.
- Record Python, Node, Yarn, Bench, MariaDB, Redis, ERPNext, Frappe, and installed app versions.
- Resolve declared required_apps versus actual installed apps before choosing the test harness. Current source may declare an integration dependency that the inspected site does not list. Do not remove production dependencies, silently fake them, or claim an integration suite passed without them.
- Production's version strings and branch names can differ from upstream packaging expectations. Pin tested actual revisions in a development manifest; do not upgrade production to make tests easier.

Implementation checkout example (commands for the future agent, not production):

~~~bash
git -C /home/bhickta/development/srv-erp fetch origin
git -C /home/bhickta/development/srv-erp worktree add -b feat/oem-catalog-foundation /home/bhickta/development/srv-erp-oem-impl origin/version-15
git -C /home/bhickta/development/srv-erp-oem-impl pull --ff-only origin version-15
~~~

If branch/path exists, inspect it and resume the matching implementation or choose a new explicit name; never delete another worktree.

Create an isolated Bench or container project at /home/bhickta/development/oem-bench, using a distinct database instance/user, Redis instance/ports, sites, logs, file store, workers, and HTTP port. App checkout/symlink targets must all be under development. Do not use /home/frappe's environment as the writable test runtime.

Development site names: oem-dev.localhost and oem-test.localhost. No production configuration JSON copied in. Use generated local development secrets and distinct DB names. Disable outbound email/integrations by local site settings and network isolation. Development workers cannot connect to production services.

Provide a repository script that refuses mutating Bench/test commands unless:

- resolved working/bench root is under /home/bhickta/development;
- site is one of the declared OEM development/test sites;
- database host/user/name and Redis endpoints match the development manifest;
- app paths are under development;
- no production site config or secret is loaded.

Use the script for all tests/migrations and CI. It fails closed; environment variables alone do not prove isolation. Never modify framework files to bypass missing dependencies.

Default fixtures are synthetic. Restoring real production backups into development is not part of this authorization. If a later staging rehearsal needs a copy, obtain operator authorization and sanitize/secure it; no restored data or files in Git or public artifacts.

Provide setup instructions that are reproducible without a production account. Test clean installation and upgrade on a synthetic legacy-like site with old settings/hook behavior represented.

## 19. Migration non-interference and whole-app risk

An additive module can still be installed by a whole srv_erp migration that invokes old after_migrate hooks. Therefore prove deployment safety, not just the new patch's safety.

Rehearsal on isolated synthetic legacy-like database:

1. Pin base branch and all installed app revisions; run existing install/migrate baseline.
2. Freeze business-table fingerprints, counts, sensitive protected field samples, and relevant settings/role/workflow states.
3. Run baseline migration again to characterize existing migration writes/jobs.
4. Start a matching database clone under the same isolated environment and apply OEM code.
5. Run OEM migration with mode Off and no imports.
6. Compare baseline-vs-OEM migration effects. New OEM table creation and namespaced transaction snapshot Custom Fields are allowed; extra changes to legacy business rows are not.
7. Explicitly inspect queued jobs and side effects from sync_brand_master_values_to_attribute, setup_masters_module, default setup, and known historical patches.
8. New DocTypes must not cause generic grid discovery to register internal OEM tables. Rename fields/structure or add a targeted exclusion with tests if necessary.
9. Run migration twice; second run creates no duplicate indexes/roles/defaults and no Items, prices, or barcodes.
10. If existing migration behavior prevents non-interference, ship a narrowly reviewed prerequisite fix or an operator-managed deployment procedure that avoids the side effect. Do not hide it by changing production settings or skipping validation.

Compare canonical protected-field data, not only counts or modified timestamps. Counts can stay equal while business meaning changes.

Business tables to verify: Item and child tables, Item Price, Item Attribute/values, Brand, Customer and permission mappings, Sales Order/Item, Delivery Note/Item, Sales Invoice/Item, Stock Entry/Detail, Stock Ledger Entry, Bin, BOM/children, Work Order, Package Barcode/Batch/Scan, relevant settings, Workflow/state/transition records, ToDo/assignments and queued work.

Metadata additions are expected. Existing metadata may be reconciled by old hooks; classify and justify every difference. No unreported changes.

## 20. Test strategy and acceptance matrix

Tests are release gates, not decoration. Use normal scoped users for permission and command tests; Administrator-only tests do not establish usable permissions.

### 20.1 Pure unit tests

- Canonical key order and option-label changes do not alter identity.
- Physical change does alter identity; customer/rate/order quantity do not.
- Printed text normalization preserves meaningful case/content.
- Decimal range/step/unit/precision; no float identity drift.
- Unknown/blank/explicit NA distinctions.
- Asset revision change, same immutable approved revision reuse.
- Rule DSL type/reference/depth/operation validation.
- Defaults precedence, locked constraints, tie conflicts, expiry, provenance.
- Parent colour/branding mapping and invalid old values.
- Fingerprints and all allowed/disallowed state transitions.

### 20.2 Real Frappe/ERPNext integration tests

- Clean install: zero new Items, prices, barcodes, existing user grants.
- Off/read-only modes: no write-through during preview/search.
- Submit missing spec: only OEM records, no staged Item.
- Approve creates one valid standalone Item and one binding.
- Existing approved spec returns same Item for authorized Customer A and B.
- Physically distinct sticker/colour/design/certification creates distinct spec.
- Rejection/cancellation/resubmission with audit and no Item deletion.
- UOM addition requires approval; existing factor cannot change.
- Legacy mapping creates metadata only and preserves all old field fingerprints.
- Ambiguous/incomplete/disabled legacy matches fail visibly.
- Duplicate physical legacy Items are not merged or modified.
- Price readiness uses valid ERPNext UOM/currency/customer/date dimensions.
- Missing blueprint/account/warehouse/company validation rolls back.
- Existing Item class and Item Price overrides still execute correctly.
- Guard catches external edits to module-created identity/UOM and detects adopted drift.
- Request/source adoption jobs and Outbox retries are idempotent.

### 20.3 Security tests

- Requester cannot approve own request by default.
- Users without module role denied; users with role but forbidden company/customer also denied.
- Search/suggestions/status/export/images reveal no inaccessible IDs/assets.
- Direct POST forgery of item_code, hash, requested_by, revision, source, or physical snapshot rejected.
- Direct REST create/update to immutable workflow records denied.
- Hidden managed fields cleared on a transaction do not bypass server binding validation.
- Old barcode generation/download routes cannot bypass managed Item/batch protections.
- Foreign saved document name or child row ID cannot be applied.
- Unsupported source doctype/field rejected.
- Input bounds, text escaping, rule injection, and file ownership tests.
- No guest access; POST enforcement and Frappe CSRF semantics verified.

### 20.4 Concurrency and rollback tests on independent connections

| Case | Required outcome |
| --- | --- |
| 20 simultaneous submits of one complete identity | One Spec + one active Request, sources preserved |
| Two approvers race on one Request | One bound Item, both authorized outcomes consistent |
| Two request attempts target same physical spec | Unique binding wins; no orphan Items |
| Barcode retries/double-click/lost response | One completed batch, same labels returned |
| Same idempotency UUID different payload | Conflict, zero extra writes |
| Item validator fails after proposed materialization | Request remains Pending, zero Item/binding/receipt |
| Mid-batch barcode insert error | No partially visible batch/labels/intent |
| Source changes while approver acts | Release safe; Apply says Stale, no order mutation |
| Catalogue/asset/default revision changes mid-flow | STALE_CONFIGURATION with preserved user draft |
| Legacy Item changed since mapping preview | Reject/quarantine, no source Item write |
| Worker/process dies before commit | No approved partial state; safe retry |
| Outbox delivery fails after approval commit | Item/request remain correct, notification retries |

Assertions inspect database contents, not mocked call counts. Test missing-row insertion races and unique-index correctness separately from FOR UPDATE behavior.

### 20.5 Browser/UAT scripts

1. Authorized salesperson opens draft order, sees customer/Brand prefills.
2. Finds base Product by model/category/card, edits only needed physical options.
3. Uses existing Item in selected empty row, normal price/UOM handlers run, no duplicate row.
4. Requests a missing configuration; draft order remains valid without placeholder Item.
5. Approver sees image/spec/default provenance and differences; approves as another scoped user.
6. Requester applies to original row after refresh; stale/deleted/submitted rows are handled safely.
7. Repeat from customer assortment with fewer inputs and correct physical identity.
8. Another authorized customer reuses the same physical Item.
9. Barcode operator configures the same spec, chooses Box, sees package and stock quantities, generates/downloads once.
10. Scan those labels into supported Stock Entry, Stock Reconciliation, and Delivery Note flows; quantities reconcile correctly.
11. Delivery/Invoice from order retains correct Item and customer authorization; commercial workflow still applies.
12. Manufacturing readiness correctly shows missing BOM and uses a verified BOM when present.
13. Existing legacy Sales Order/barcode workflows still work with all flags Off and while pilot enabled elsewhere.
14. Slow responses / rapid Product changes never restore stale values.
15. Keyboard/mobile/accessibility and permission failure recovery.
16. Existing parent-copy scripts cannot silently change managed physical branding.

Synthetic fixtures include 30 Products, multiple Item Groups, 3 Brands, 4 Customers, 2 Companies, enum/numeric/custom artwork schemas, missing defaults, one ambiguous legacy duplicate group, stock-UOM Box products, and multiple packaging conversions.

Performance dataset: at least 50,000 legacy Items, 500 Products, and 5,000 OEM Specifications, plus representative barcode volume, all synthetic. Do not use production data to generate public screenshots.

### 20.6 Performance targets

Targets are budgets to measure on declared development hardware, not promises inferred from code:

- Product search server p95 <=250 ms at representative size.
- Configuration/default resolution p95 <=500 ms.
- Exact binding lookup p95 <=150 ms.
- Submit/approve without external notification p95 <=1 s, excluding lock contention.
- UI gives immediate load feedback <=100 ms and usable catalogue <=1 s on normal LAN.
- Legacy document save overhead from OEM code p95 <=20 ms on mode Off/no managed Items.
- Barcode batch cap 500 synchronously; larger demand needs an explicit benchmark and separately reviewed async intent model before enabling.

Use indexed bounded queries, no wildcard full-table attribute Cartesian scans, no N+1 Product card metadata or customer history calls. Cache immutable published config by hash; scope context/user permissions and never cache inaccessible results globally.

Use before/after measurements from the same dataset. Record query counts, plans, p50/p95, and uncertainty.

## 21. Ordered implementation work packages

Do one package at a time. Each requires a focused commit, tests/evidence, updated WORK_LOG.md, and a reviewed diff before continuing. Do not skip directly to the UI.

P00 — Reconnaissance and isolated environment.
Outputs: exact baseline/dependency manifest, development guard, synthetic test site, baseline existing tests, no production connections.
Acceptance: safe script refuses production paths/endpoints. Resolve declared integration dependency mismatch in development.
Commit: chore(oem): establish isolated development and baseline checks.

P01 — ADRs and contracts.
Outputs: architecture.md, ADRs for stock identity, independent module, approval atomicity, packaging/UOM, legacy adoption, permissions, price/manufacturing readiness; api.md and schema glossary.
Acceptance: confirmed business rules represented; all new Item fields allowlisted; no unspecified automatic migration.
Commit: docs(oem): define identity and integration contracts.

P02 — Pure domain.
Outputs: typed models, canonicalization, transitions, packaging, fingerprints.
Acceptance: unit tests demonstrate same/different identity, decimals, explicit NA, text semantics.
Commit: feat(oem): implement physical specification domain.

P03 — Config rules and defaults.
Outputs: pure bounded DSL, scope resolver, provenance.
Acceptance: ties/locks/staleness/errors predictable; no eval/exec or silent invalid defaults.
Commit: feat(oem): add typed rules and contextual defaults.

P04 — Module schemas, indexes, and role definitions.
Outputs: OEM module entry, real package, specified DocTypes, controllers, disabled settings, OEM-only index patch.
Acceptance: clean install and second migrate create no legacy business records or user role grants; internal OEM children not discovered as old item grids.
Commit: feat(oem): add isolated catalogue schemas and settings.

P05 — Publication/asset/customer-brand services.
Outputs: validated draft/publish/clone lifecycle, approved immutable file revisions, manager association editor.
Acceptance: identity semantics immutable; invalid account/company/asset/default rejected; Brand master never saved as association side effect.
Commit: feat(oem): publish governed catalogue and context masters.

P06 — Repositories and permission boundaries.
Outputs: scoped Frappe repositories, authorization ports, batch binding/fingerprint lookup, DTO parser/error envelope.
Acceptance: normal-user scope/security tests and no unrestricted search.
Commit: feat(oem): add scoped repositories and authorization.

P07 — Read configuration/search/preview APIs.
Outputs: bounded Product cards, defaults/provenance, complete pure preview, readiness interfaces.
Acceptance: repeated previews produce zero business writes; cache respects user/context; similar matches never auto-resolve.
Commit: feat(oem): expose read-only guided configuration APIs.

P08 — Requests/drafts/source intents/idempotency.
Outputs: explicit draft save, immutable submit, active-key uniqueness, private sources, reject/cancel.
Acceptance: no staged Items, preserved multiple sources, replay/conflict semantics, submit race tests.
Commit: feat(oem): add idempotent configuration requests.

P09 — Atomic approval/Item materializer.
Outputs: allowlisted Item creation, spec locks, unique binding, decision snapshots, scoped capability.
Acceptance: independent-connection approval races, controller failure rollback, maker-checker normal-user tests.
Commit: feat(oem): atomically release and bind physical items.

P10 — Readiness/pricing/manufacturing checklist.
Outputs: standard pricing adapter, company/UOM checks, manufacturing evidence dashboard; optional reviewed explicit price provisioning.
Acceptance: standalone Item does not rely on variant price/BOM inheritance; missing readiness blocks the correct action only.
Commit: feat(oem): validate sales barcode and manufacturing readiness.

P11 — Legacy bootstrap/adoption review.
Outputs: preview/approve/apply plans, source fingerprint check, bounded resumable OEM-only imports, duplicate/missing metadata conflicts.
Acceptance: field-level before/after fingerprints prove zero legacy changes; no automatic bulk import.
Commit: feat(oem): add non-mutating legacy item adoption.

P12 — Shared configurator and catalogue page.
Outputs: components/store/api client, Product cards, context, prefilled controls, assets, package preview, review, drafts/status.
Acceptance: browser stale-response, keyboard/mobile, empty/error and no-image states; no transaction writes yet.
Commit: feat(oem): build guided catalogue configurator.

P13 — Sales Order adapter and Brand compatibility.
Outputs: scoped buttons/side panel/row context, namespaced row fields, application DTO, old lookup bridge, physical-default reconciliation.
Acceptance: no Item-less row, no auto-save, parent scripts cannot corrupt spec, managed server enforcement even if fields cleared, old workflow unchanged.
Commit: feat(oem): integrate safe sales order item configuration.

P14 — Barcode adapter and protected UOMs.
Outputs: configure button, authorized idempotent generation/download, batch snapshot fields, old endpoint managed-policy checks.
Acceptance: package vs stock quantities visible, retries one batch, scan-chain tests, immutable factors, mixed-UOM unsafe managed flow blocked.
Commit: feat(oem): integrate governed barcode generation.

P15 — Downstream compatibility and integrity.
Outputs: focused transaction guards, binding drift/quarantine review, known print/report assumptions handled minimally.
Acceptance: delivery/invoice/stock/manufacturing supported paths work; legacy returns/cancellation safe; no wildcard hook.
Commit: feat(oem): enforce managed integrity across supported flows.

P16 — Notifications, audit, observability, support.
Outputs: transactional Outbox, notifications/assignment after commit, scheduled retry scoped to new events, scoped audit/report dashboards.
Acceptance: notification failure cannot break approved inventory state; delivery idempotent, logs redacted, actionable correlation IDs.
Commit: feat(oem): add auditable operations and reliable notifications.

P17 — Migration and performance proof.
Outputs: base-vs-OEM migration comparison, SQL plans and representative synthetic benchmarks, security/concurrency regression runs.
Acceptance: section 19 zero-extra-business-change invariant, section 20 targets/release gates. Implement focused prerequisite fixes if measured.
Commit: test(oem): verify isolation concurrency and legacy compatibility.

P18 — Documentation, UAT, rollout packaging.
Outputs: operator-runbook.md, user-guide.md, troubleshooting, UI screenshots with synthetic data, release checklist, rollback drill, support owner.
Acceptance: a second operator can reproduce clean setup/pilot/off-mode rollback; all supported limitations explicit.
Commit: docs(oem): document rollout operations and acceptance.

P19 — Final review and PR.
Outputs: reviewed focused diff, passing required CI, exact test evidence, risk/limitation list, PR(s) against version-15.
Acceptance: no private production audit/data, no generated artifacts/secrets, no automatic enablement, no deployment or merge.

Suggested PR boundaries: foundation P00-P07, lifecycle/adoption P08-P11, shared UI/Sales Order P12-P13, barcode/downstream P14-P15, production gates P16-P19. Keep incomplete features disabled throughout. PRs need integration testing on their combined final state before release. A draft PR is appropriate while a dependency chain is incomplete.

## 22. Agent execution and context-compaction protocol

Create docs/oem-item-management/WORK_LOG.md in the implementation worktree. Keep:

- Objective and immutable constraints.
- Baseline commit and isolated bench/site/ports.
- Current package Pxx.
- Completed outputs, commit hashes, exact test commands/results.
- Decisions/ADRs and why.
- Known failures or prerequisites.
- Next three concrete actions.
- Any required operator decisions without broad speculative questions.

At every package boundary:

1. Read the corresponding contract sections.
2. Inspect relevant current code; plan is a baseline, not a substitute for current source.
3. Add only that package's implementation.
4. Run its required checks in the guarded isolated environment.
5. Review diff and avoid unrelated formatting.
6. Update WORK_LOG and commit.
7. Continue to the next package.

If context is lost, read IMPLEMENTATION_PLAN, HANDOFF, WORK_LOG, and current git status/log. Do not restart or repeat completed migrations blindly.

Before marking done, run the full acceptance matrix and verify every stated supported adapter. Report blocked tests honestly. If no working isolated Bench is available, domain/unit progress is useful but cannot be labeled a complete production-ready solution.

Do not deploy, merge, change live settings, or perform live data adoption just because the implementation command asks to finish.

## 23. Operations, monitoring, and maintenance

Operational dashboard/report surfaces:

- Pending requests by age and authorized approver.
- Stale sources requiring user Apply/reconfigure.
- Unbound/incomplete Product specifications.
- Legacy adoption conflicts and suspected duplicates.
- Quarantined Item bindings and fingerprint reason.
- Products with missing prices/company defaults/BOM/readiness.
- Outbox retries/dead letters.
- New Item count per released specification and period.
- Barcode intents with missing/inconsistent completed batches.
- Configuration publication changes and affected future inputs.

Useful metrics: exact reuse vs create rate, configuration completion time, missing/invalid defaults, request wait time, approval failure codes, collisions/idempotency conflicts, drift detections, notification retry backlog, query latency, unsupported UOM errors. Avoid metric labels containing customer names, artwork, Item IDs, or unbounded identity hashes.

Audit every config publication, association approval, request/decision, Item creation/binding, UOM addition, import plan apply, quarantine, pilot setting, and self-approval policy change. Use append-only business events; ordinary Frappe Version logs supplement rather than replace them.

Retention:

- Specifications/bindings/approval/import/audit records persist while referenced.
- Private drafts may expire after configured period; cleanup applies only to unreferenced drafts, with a dry-run and explicit retention setting.
- Command receipts retained at least through the retry window and permanently for Item release/barcode generation where needed for durable business replay.
- Outbox payloads store IDs; prune delivered technical events after configured retention while retaining business audit.
- Referenced approved assets cannot be overwritten/deleted.
- Approved Asset Revision permission checks extend to referenced File update/delete/upload routes. Validate file path ownership and checksum when using an asset; external byte drift is a conflict. Never fetch arbitrary external URLs or read a client-supplied filesystem path.

Reconciliation job reads new bindings/intents and reports inconsistencies. It may append OEM audit events and quarantine inconsistent OEM bindings through the authorized integrity command. It does not auto-fix legacy records, recreate deleted Items, re-enable disabled masters, generate labels, or alter stock.

## 24. Rollout plan and actual authorization gates

Stage A — Development.
All work under development; synthetic data; full tests. No production activation.

Stage B — Reviewable PRs.
Small commits/PRs; no merge by agent. Screenshots contain synthetic examples. Private production audit stays local.

Stage C — Operator-approved staging rehearsal.
Production-like sanitized dataset if separately authorized, verified dependency versions, disabled outbound integrations, legacy workflow smoke tests, two consecutive migrations, before/after fingerprints, rollback drill.

Stage D — Schema deployment with mode Off.
Performed by production operator after review and backup/recovery verification. All flags disabled. Verify zero unexpected legacy business changes and job side effects before enabling anything.

Stage E — Read-only pilot.
Publish a handful of reviewed Product schemas/assets/defaults, explicit customer-brand associations. Operators compare configurations and candidate Item reuse without stock writes.

Stage F — Adoption-only pilot.
allow_create_items=false. Bind a few fully verified existing Items through approved plans. Demonstrate Sales Order and barcode flows using existing codes. Customer histories/stock/old barcodes remain intact.

Stage G — Controlled new-item pilot.
Only selected products/users/companies. At least requester+separate approver available. Enable one adapter at a time. Approve a small real-needed spec, provision readiness through reviewed ERPNext processes, reconcile transaction/label quantities.

Stage H — Gradual active use.
Expand by verified Product family and user group based on acceptance metrics. No blanket import of every existing variant.

Stage I — Stop future legacy Cartesian generation.
This is a separate explicit operator configuration change, after legacy usage/dependencies are understood:
auto_create_variants_on_brand_update=0 and allow_bulk_variant_creation=0 may be appropriate.
Do not infer that turning these off alone stops every already queued job or manual path. Check job guards, UI/server bulk endpoints, scripts, integrations, and installed app hooks. Preserve settings snapshot and reversal procedure. Do not change approval enforcement globally without assessing legacy users/flows.

Stage J — Future legacy archival project.
Separate authorization, all-reference analysis, stock/WIP/integration reconciliation. Not included here.

Before production activation require named catalogue owner, approval owner, rollout operator, support owner, Product identity classifications, mappings/defaults, pricing/BOM readiness policy, known supported UOM flows, verified backups, and passed mandatory tests.

These are deployment gates, not reasons to stop coding early. Implement safe defaults and review screens while operator decisions remain open.

## 25. Rollback and failure handling

Distinguish feature rollback, code rollback, and data recovery:

- Creation kill switch: allow_create_items=false immediately prevents new stock/UOM writes.
- UI/feature rollback: disable picker flags and mode Off; return operators to normal ERPNext/legacy paths.
- Already created ordinary Items and completed transactions remain usable; no deletion or disabling as rollback.
- Leave OEM metadata and integrity protection installed so physical identity remains auditable.
- A software downgrade must not leave unresolved hook imports or missing managed integrity validators. Prefer forward fix/compatible disabled release; rehearse any code revert against the actual database version.
- Never drop OEM tables or namespaced fields during incident response.
- Approved physical mistakes: quarantine for new use, preserve stock and history, investigate and follow ordinary controlled inventory correction process. Do not change Item meaning.
- Incorrect binding discovered after transactions: quarantine and record repair case; no direct stock_item reassignment.
- UOM/config error: block future generation, keep old factors and existing barcodes unchanged, use approved new UOM/spec path.
- Notification outage: retry Outbox; approval state is already durable.
- Failed schema migration: operator restores/verifies backup or deploys reviewed forward fix; agent does not touch production.
- No restore of an old production backup after new business transactions without an operator reconciliation/recovery plan.

Run a rollback drill on isolated staging: pilot create/use Item -> flags Off -> legacy and new concrete Items transact safely -> no new OEM creation -> audit still available.

## 26. Definition of production-ready

All conditions required:

- One physical identity per released spec, one active binding, no wildcard legacy reuse.
- Exact stock sharing across authorized customers proven.
- Pending/rejected/cancelled requests create zero Items.
- Full identity/default/asset/UOM validation and visible provenance.
- Approval and barcode concurrency/rollback/idempotency proven on a real database.
- Normal-user permission tests, direct API bypass tests, protected file/export checks.
- Installation/migration Off-mode creates no extra legacy business mutations.
- Safe explicit legacy adoption with complete evidence and unchanged old fields.
- Sales Order, Brand lookup, barcode, scan transactions, downstream pricing/manufacturing readiness work for stated supported paths.
- Existing legacy workflows continue with Off mode and outside pilot.
- Representative performance measured and acceptable.
- Operator/UAT documentation, synthetic screenshots, rollback drill, monitoring, support ownership.
- Required CI passed; limitations/release gates recorded honestly.
- PR reviewed; production activation remains a separate operator action.

## 27. Open operator decisions with safe development defaults

| Decision | Development default and implementation action |
| --- | --- |
| Which templates/base models are the true portfolio Products? | Bootstrap preview only; do not auto-merge or impose a portfolio count |
| Which packaging/certification facts split physical stock? | Model them as configurable identity attributes; default to distinct when stock suitability is uncertain |
| Which existing Brand associations are authorized? | Manager-reviewed many-to-many records; history only a suggestion |
| Mapping legacy Colour vs transaction Color vs branding_type/marketed_by | Explicit reviewed mapping editor; no label-only equality |
| Which legacy Item is canonical among duplicates? | Manager-selected eligible binding; no stock movement/merge |
| Who are approvers and pilot users? | Role definitions only, no assignments |
| Valid company accounting/warehouse/pricing/BOM defaults? | Required readiness checks; no fabricated values |
| Existing Force Barcode Only mixed-UOM requirements? | Supported fixed-UOM path, explicit managed-case block for unsafe combinations |
| Should exact non-physical stock-sharing occur across Brands? | Physical Brand included; unbranded stock represented explicitly |
| Timing of old auto/bulk creation disablement? | Operator change after pilot; no installer action |

The answers already given about customer sharing and relevant customizations are fixed requirements, not questions to re-ask.

## 28. References and source-of-truth priority

Priority: user rules and confirmed business decisions -> current repository/runtime evidence -> this contract -> current official documentation. Document a focused ADR if current code makes a specified mechanism impossible; preserve the underlying invariant.

Official supporting documentation:

- [ERPNext Item Variants](https://docs.frappe.io/erpnext/item-variants): templates organize attribute-based variations; actual transactional Items represent concrete variants. This supports retaining concrete inventory identity, not generating every combination.
- [ERPNext selling in different UOMs](https://docs.frappe.io/erpnext/Selling-in-different-UOM): one Item can transact in several UOMs with a stock-UOM conversion. Physical package identity still needs the business classification in this plan.
- [OpenAI developer commands](https://learn.chatgpt.com/docs/developer-commands?surface=cli): general CLI command reference. The handoff command was also verified against this machine's installed codex --help.

Do not copy large documentation excerpts. Runtime behavior is verified against the pinned code and tests because upstream documentation can describe a different release.
