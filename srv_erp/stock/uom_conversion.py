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


def analyze_item(item_code: str) -> dict:
    """Analyze a single item for UOM conversion feasibility.

    Returns a dict with item metadata, transaction status, and the
    recommended conversion strategy.
    """
    item = frappe.get_doc("Item", item_code)

    item_type = "Standard"
    if item.has_variants:
        item_type = "Template"
    elif item.variant_of:
        item_type = "Variant"

    has_transactions = bool(
        frappe.db.exists("Stock Ledger Entry", {"item_code": item_code})
    )

    has_open_quantities = _has_open_bin_quantities(item_code)

    strategy = "Duplicate & Disable" if (has_transactions or has_open_quantities) else "Direct"

    result = {
        "item_code": item_code,
        "item_name": item.item_name,
        "item_type": item_type,
        "variant_of": item.variant_of or "",
        "current_stock_uom": item.stock_uom,
        "has_transactions": 1 if has_transactions else 0,
        "has_open_quantities": 1 if has_open_quantities else 0,
        "strategy": strategy,
    }

    if item_type == "Template":
        result["variants"] = frappe.get_all(
            "Item", filters={"variant_of": item_code}, pluck="name"
        )

    return result


def _has_open_bin_quantities(item_code: str) -> bool:
    """Check whether the item has any open (non-zero) quantities in Bin."""
    bins = frappe.get_all(
        "Bin",
        filters={"item_code": item_code},
        fields=["reserved_qty", "ordered_qty", "indented_qty", "planned_qty"],
    )
    for b in bins:
        if any(
            flt(b.get(f)) > 0
            for f in ("reserved_qty", "ordered_qty", "indented_qty", "planned_qty")
        ):
            return True
    return False


def analyze_conversion(doc) -> list[dict]:
    """Produce the full list of items that a Stock UOM Conversion will affect.

    Supports both 'Single Item' mode and 'Batch Filter' mode.
    """
    items = []
    
    if doc.selection_mode == "Single Item":
        primary = analyze_item(doc.item_code)
        items = [_analysis_to_row(primary)]

        if primary["item_type"] == "Template" and doc.include_variants:
            allow_different_uom = frappe.db.get_single_value(
                "Item Variant Settings", "allow_different_uom"
            )
            for variant_code in primary.get("variants", []):
                variant_uom = frappe.db.get_value("Item", variant_code, "stock_uom")
                if allow_different_uom and variant_uom != cstr(doc.current_stock_uom):
                    continue
                variant = analyze_item(variant_code)
                items.append(_analysis_to_row(variant))
                
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
        allow_different_uom = frappe.db.get_single_value(
            "Item Variant Settings", "allow_different_uom"
        )
        
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
                        
        for item_code in final_item_codes:
            items.append(_analysis_to_row(analyze_item(item_code)))

    return items


def _analysis_to_row(analysis: dict) -> dict:
    """Convert an analysis dict into a child-table row dict."""
    return {
        "item_code": analysis["item_code"],
        "item_name": analysis["item_name"],
        "item_type": analysis["item_type"],
        "current_stock_uom": analysis["current_stock_uom"],
        "has_transactions": analysis["has_transactions"],
        "has_open_quantities": analysis["has_open_quantities"],
        "strategy": analysis["strategy"],
        "status": "Pending",
    }


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

    for row in doc.items:
        try:
            if row.strategy == "Direct":
                _convert_direct(doc, row, log_entries)
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


def _convert_direct(doc, row, log_entries: list[dict]):
    """Change stock_uom in-place — only works when no SLE exists."""
    item = frappe.get_doc("Item", row.item_code)
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
    """Create a new Item with the target UOM and disable the original."""
    old_item = frappe.get_doc("Item", row.item_code)

    # --- Build the new item ------------------------------------------------
    new_item = frappe.copy_doc(old_item)

    # Reset identity / audit fields that copy_doc retains
    new_item.item_code = _generate_unique_item_code(
        old_item.item_code, doc.new_stock_uom
    )
    new_item.item_name = old_item.item_name  # keep original name
    new_item.stock_uom = doc.new_stock_uom
    new_item.disabled = 0
    new_item.uoms = []  # Will be re-populated by item.add_default_uom_in_conversion_factor_table on save

    # Handle template → variant linkage
    if old_item.variant_of and old_item.variant_of in template_mapping:
        new_item.variant_of = template_mapping[old_item.variant_of]

    new_item.flags.ignore_mandatory = False
    new_item.insert(ignore_permissions=False)

    # If this was a template item, remember the mapping for its variants
    if old_item.has_variants:
        template_mapping[old_item.item_code] = new_item.name

    _log_action(
        doc.name,
        row.item_code,
        "Item Duplicated",
        old_item.item_code,
        new_item.name,
        f"New item {new_item.name} created with stock_uom={doc.new_stock_uom}.",
    )
    log_entries.append({
        "action": "Item Duplicated",
        "item_code": row.item_code,
        "details": f"→ {new_item.name}",
    })

    # --- Disable the old item -----------------------------------------------
    old_item.disabled = 1
    old_item.save()

    _log_action(
        doc.name,
        row.item_code,
        "Item Disabled",
        "Enabled",
        "Disabled",
        f"Original item {old_item.item_code} disabled after duplication.",
    )
    log_entries.append({
        "action": "Item Disabled",
        "item_code": row.item_code,
        "details": f"{old_item.item_code} disabled",
    })

    # --- Update the conversion doc row --------------------------------------
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


# ---------------------------------------------------------------------------
# Item-code generation
# ---------------------------------------------------------------------------


def _generate_unique_item_code(base_code: str, new_uom: str) -> str:
    """Generate a unique item code by appending a UOM-based suffix.

    Examples:
        ITEM-001 + Mtr  → ITEM-001-MTR
        ITEM-001 + Mtr  → ITEM-001-MTR-1  (if -MTR already exists)
    """
    # Clean up the UOM name for use as suffix
    suffix = new_uom.strip().upper().replace(" ", "-")[:6]
    candidate = f"{base_code}-{suffix}"

    if not frappe.db.exists("Item", candidate):
        return candidate

    counter = 1
    while frappe.db.exists("Item", f"{candidate}-{counter}"):
        counter += 1
    return f"{candidate}-{counter}"
