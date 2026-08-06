"""
Stock UOM Conversion Engine

Non-destructive conversion of Item stock_uom:
- Direct: change in-place when no stock transactions exist (ERPNext allows this natively).
- Duplicate & Disable: create a new Item with the target UOM and disable the original.

All operations go through ERPNext's own Item.save() / Item.insert() so standard
validations (check_stock_uom_with_bin, validate_uom, etc.) are never bypassed.
"""

import frappe
from frappe import _
from frappe.utils import cstr, flt


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------

def analyze_conversion(doc) -> list[dict]:
    """Produce the full list of items that a Stock UOM Conversion will affect.

    Supports both 'Single Item' mode and 'Batch Filter' mode.
    """
    items = []
    
    if doc.selection_mode == "Single Item":
        final_item_codes = {doc.item_code}
        if doc.include_variants:
            has_variants = frappe.db.get_value("Item", doc.item_code, "has_variants")
            if has_variants:
                variants = frappe.get_all("Item", filters={"variant_of": doc.item_code}, pluck="name")
                for variant_code in variants:
                    final_item_codes.add(variant_code)
                    
        items = _analyze_items_bulk(list(final_item_codes), doc.new_stock_uom)
        
    elif doc.selection_mode == "Batch Filter":
        filters = []
        
        if doc.filter_item_group:
            # Include child item groups
            lft, rgt = frappe.db.get_value("Item Group", doc.filter_item_group, ["lft", "rgt"])
            item_groups = frappe.db.sql_list(
                "select name from `tabItem Group` where lft >= %s and rgt <= %s", (lft, rgt)
            )
            if item_groups:
                filters.append(["item_group", "in", item_groups])
            else:
                filters.append(["item_group", "=", doc.filter_item_group])
                
        if doc.filter_brand:
            filters.append(["brand", "=", doc.filter_brand])
            
        if doc.filter_current_stock_uom:
            filters.append(["stock_uom", "=", doc.filter_current_stock_uom])
            
        if doc.filter_disabled == "Active Only":
            filters.append(["disabled", "=", 0])
        elif doc.filter_disabled == "Disabled Only":
            filters.append(["disabled", "=", 1])
            
        if doc.filter_item_type == "Standard":
            filters.append(["has_variants", "=", 0])
            filters.append(["variant_of", "in", ("", None)])
        elif doc.filter_item_type == "Template":
            filters.append(["has_variants", "=", 1])
        elif doc.filter_item_type == "Variant":
            filters.append(["variant_of", "not in", ("", None)])
            
        # First, find the primary items matching the filters
        matched_items = frappe.get_all("Item", filters=filters, pluck="name")
        
        # If we need to include variants of matched templates
        include_variants = doc.filter_has_variants == "Yes — Include Variants"
        try:
            allow_different_uom = frappe.db.get_single_value(
                "Item Variant Settings", "allow_different_uom"
            )
        except Exception:
            allow_different_uom = 0
        
        final_item_codes = set()
        for item_code in matched_items:
            final_item_codes.add(item_code)
            
            if include_variants:
                has_variants = frappe.db.get_value("Item", item_code, "has_variants")
                if has_variants:
                    variants = frappe.get_all("Item", filters={"variant_of": item_code}, pluck="name")
                    for variant_code in variants:
                        variant_uom = frappe.db.get_value("Item", variant_code, "stock_uom")
                        # Skip if variant has a different UOM and it's allowed
                        if allow_different_uom and doc.filter_current_stock_uom and variant_uom != doc.filter_current_stock_uom:
                            continue
                        final_item_codes.add(variant_code)
                        
        items = _analyze_items_bulk(list(final_item_codes), doc.new_stock_uom)

    return items


def _analyze_items_bulk(item_codes: list[str], target_uom: str = None) -> list[dict]:
    if not item_codes:
        return []

    # 1. Bulk fetch item metadata
    items_data = frappe.get_all(
        "Item",
        filters={"name": ("in", item_codes)},
        fields=["name", "item_name", "has_variants", "variant_of", "stock_uom"]
    )

    # 2. Bulk fetch transaction existence
    sle_items = frappe.get_all(
        "Stock Ledger Entry",
        filters={"item_code": ("in", item_codes)},
        pluck="item_code",
        distinct=True
    )
    sle_set = set(sle_items)

    # 3. Bulk fetch open bin quantities (chunked to avoid IN limits)
    bin_set = set()
    chunk_size = 2000
    for i in range(0, len(item_codes), chunk_size):
        chunk = tuple(item_codes[i : i + chunk_size])
        bin_data = frappe.db.sql(
            """
            SELECT item_code 
            FROM `tabBin` 
            WHERE item_code IN %s 
            AND (reserved_qty > 0 OR ordered_qty > 0 OR indented_qty > 0 OR planned_qty > 0)
            """,
            (chunk,),
            as_dict=True
        )
        for b in bin_data:
            bin_set.add(b.item_code)

    results = []
    for d in items_data:
        # Skip items that ALREADY have the target UOM
        if target_uom and cstr(d.stock_uom) == cstr(target_uom):
            continue

        item_type = "Standard"
        if d.has_variants:
            item_type = "Template"
        elif d.variant_of:
            item_type = "Variant"

        has_trans = 1 if (d.name in sle_set) else 0
        has_open = 1 if (d.name in bin_set) else 0
        strategy = "Duplicate & Disable" if (has_trans or has_open) else "Direct"

        results.append({
            "item_code": d.name,
            "item_name": d.item_name,
            "item_type": item_type,
            "variant_of": d.variant_of or "",
            "current_stock_uom": d.stock_uom,
            "has_transactions": has_trans,
            "has_open_quantities": has_open,
            "strategy": strategy,
            "status": "Pending",
        })

    return results


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def execute_conversion(doc):
    """Run the actual UOM conversion for every row in ``doc.items``.

    Called from ``StockUOMConversion.on_submit``.
    """
    log_entries: list[dict] = []
    # Tracks old_template_code -> new_template_code so that duplicated
    # variants can be re-linked to the new template.
    template_mapping: dict[str, str] = {}

    # Sort items so that:
    # 1. Template (Duplicate): Creates new template ID.
    # 2. Variant (Duplicate): Unlinks from old template, preventing auto-cascade crash on old template.
    # 3. Template (Direct): Changes UOM, safely auto-cascades to remaining linked direct variants.
    # 4. Variant (Direct): Safely re-saves and matches the already-updated template UOM.
    def _sort_key(r):
        if r.item_type == "Template":
            return 0 if r.strategy == "Duplicate & Disable" else 2
        return 1 if r.strategy == "Duplicate & Disable" else 3

    sorted_items = sorted(doc.items, key=_sort_key)

    for row in sorted_items:
        try:
            if row.strategy == "Direct":
                _convert_direct(doc, row, log_entries, template_mapping)
            elif row.strategy == "Duplicate & Disable":
                _convert_duplicate(doc, row, log_entries, template_mapping)
            else:
                row.db_set("status", "Skipped")
                row.db_set("remarks", "Unknown strategy")
        except Exception as e:
            frappe.log_error(
                message=frappe.get_traceback(),
                title=f"Stock UOM Conversion Error: {row.item_code}",
            )
            row.db_set("status", "Failed")
            row.db_set("remarks", cstr(e)[:500])
            log_entries.append({
                "action": "Failed",
                "item_code": row.item_code,
                "details": cstr(e),
            })

    # Persist the human-readable conversion log
    log_text = _build_log_text(log_entries)
    existing_log = doc.conversion_log or ""
    doc.db_set("conversion_log", (existing_log + "\n" + log_text).strip())


def _convert_direct(doc, row, log_entries: list[dict], template_mapping: dict):
    """Change stock_uom in-place — only works when no SLE exists."""
    item = frappe.get_doc("Item", row.item_code)
    
    # If this is a variant, and its template was duplicated, we must re-link it
    if item.variant_of and item.variant_of in template_mapping:
        frappe.db.set_value("Item", item.item_code, "variant_of", template_mapping[item.variant_of])
        item.variant_of = template_mapping[item.variant_of]

    old_uom = item.stock_uom
    item.stock_uom = doc.new_stock_uom
    # ERPNext's validate_uom / check_stock_uom_with_bin will run here.
    item.save()

    _log_action(
        doc.name,
        row.item_code,
        "UOM Changed",
        old_uom,
        doc.new_stock_uom,
        f"Stock UOM updated directly from {old_uom} to {doc.new_stock_uom}.",
    )
    log_entries.append({
        "action": "UOM Changed",
        "item_code": row.item_code,
        "details": f"{old_uom} → {doc.new_stock_uom}",
    })
    row.db_set("status", "Converted")


def _convert_duplicate(doc, row, log_entries: list[dict], template_mapping: dict):
    """Rename the old item to -OLD, create new item with original code, and move stock."""
    original_item_code = row.item_code
    
    # 1. Generate suffix for old item
    old_suffix = "-OLD"
    counter = 1
    while frappe.db.exists("Item", f"{original_item_code}{old_suffix}"):
        old_suffix = f"-OLD-{counter}"
        counter += 1
    new_old_item_code = f"{original_item_code}{old_suffix}"

    # 2. Rename old item in DB (this cascades to all historical docs)
    frappe.flags.ignore_permissions = True
    frappe.rename_doc("Item", original_item_code, new_old_item_code, force=True)
    frappe.flags.ignore_permissions = False
    
    # Fetch the newly renamed old item
    old_item = frappe.get_doc("Item", new_old_item_code)

    # 3. Build the new item (using the original item_code)
    new_item = frappe.copy_doc(old_item)
    new_item.item_code = original_item_code
    new_item.item_name = old_item.item_name  # keep original name
    new_item.stock_uom = doc.new_stock_uom
    new_item.disabled = 0
    new_item.uoms = []  # Re-populated automatically on save

    # Handle template → variant linkage
    old_variant_of = old_item.variant_of
    
    # Unlink the old item if it was a variant (prevents auto-cascade from old template)
    if old_variant_of:
        frappe.db.set_value("Item", old_item.item_code, "variant_of", "")
        old_item.variant_of = ""
        
    if old_variant_of and old_variant_of in template_mapping:
        new_item.variant_of = template_mapping[old_variant_of]

    new_item.flags.ignore_mandatory = False
    new_item.insert(ignore_permissions=True)

    # If this was a template item, remember the mapping for its variants
    if old_item.has_variants:
        template_mapping[new_old_item_code] = new_item.name

    _log_action(
        doc.name,
        original_item_code,
        "Item Duplicated",
        new_old_item_code,
        new_item.name,
        f"Original renamed to {new_old_item_code}. New created as {new_item.name} ({doc.new_stock_uom}).",
    )
    log_entries.append({
        "action": "Item Duplicated",
        "item_code": original_item_code,
        "details": f"Old → {new_old_item_code}",
    })

    # 4. Move Stock (1:1 Repack)
    # Temporarily enable the old item so we can move stock out of it (Stock Entry validation requires active items)
    if old_item.disabled:
        old_item.disabled = 0
        old_item.save(ignore_permissions=True)

    bins = frappe.get_all(
        "Bin", 
        filters={"item_code": new_old_item_code, "actual_qty": (">", 0)}, 
        fields=["warehouse", "actual_qty"]
    )
    if bins:
        # Group bins by company because Stock Entry is company-specific
        company_bins = {}
        for b in bins:
            company = frappe.db.get_value("Warehouse", b.warehouse, "company")
            if not company:
                company = frappe.defaults.get_user_default("company")
            company_bins.setdefault(company, []).append(b)

        for company, c_bins in company_bins.items():
            se = frappe.new_doc("Stock Entry")
            se.purpose = "Repack"
            se.stock_entry_type = "Repack"
            se.company = company
            se.set_posting_time = 1
            se.posting_date = frappe.utils.today()
            
            for b in c_bins:
                qty = flt(b.actual_qty)
                # Source row (consume old item)
                se.append("items", {
                    "item_code": new_old_item_code,
                    "s_warehouse": b.warehouse,
                    "qty": qty,
                    "uom": old_item.stock_uom,
                    "conversion_factor": 1.0,
                })
                # Target row (produce new item)
                se.append("items", {
                    "item_code": original_item_code,
                    "t_warehouse": b.warehouse,
                    "qty": qty,
                    "uom": doc.new_stock_uom,
                    "conversion_factor": 1.0,
                })
                
            se.set_stock_entry_type()
            se.insert(ignore_permissions=True)
            se.submit()
            
            log_entries.append({
                "action": "Stock Moved",
                "item_code": original_item_code,
                "details": f"Via {se.name} ({company})",
            })
    # 5. Disable the old item
    old_item.disabled = 1
    old_item.save(ignore_permissions=True)

    # --- Update the conversion doc row ---
    row.db_set("status", "Converted")
    row.db_set("new_item_code", new_item.name)

    # Set top-level result fields for the primary item
    if row.item_code == doc.item_code:
        doc.db_set("new_item_code", new_item.name)
        doc.db_set("old_item_disabled", 1)


# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------


def _log_action(
    conversion_name: str,
    item_code: str,
    action: str,
    old_value: str = "",
    new_value: str = "",
    details: str = "",
):
    """Create a ``Stock UOM Conversion Log`` entry."""
    log = frappe.new_doc("Stock UOM Conversion Log")
    log.conversion = conversion_name
    log.item_code = item_code
    log.action = action
    log.old_value = cstr(old_value)
    log.new_value = cstr(new_value)
    log.details = details
    log.insert(ignore_permissions=True)
    return log


def _build_log_text(entries: list[dict]) -> str:
    """Format log entries into a human-readable text block."""
    lines: list[str] = []
    for entry in entries:
        action = entry.get("action", "")
        item = entry.get("item_code", "")
        detail = entry.get("details", "")
        lines.append(f"[{action}] {item}: {detail}")
    return "\n".join(lines)


