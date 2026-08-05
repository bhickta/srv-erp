"""Stock UOM Conversion DocType controller.

Provides a safe, audited workflow for changing an Item's stock_uom:
1.  User picks an item and the desired new UOM.
2.  ``analyze()`` populates the Affected Items table with per-item
    transaction status and the recommended strategy (Direct vs Duplicate).
3.  On Submit the conversion engine executes every row.
"""

import frappe
from frappe import _
from frappe.model.document import Document

from srv_erp.stock.uom_conversion import analyze_conversion, execute_conversion


class StockUOMConversion(Document):
    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------

    def validate(self):
        self._validate_uom_different()
        if self.selection_mode == "Single Item":
            self._detect_item_type()
            self._validate_variant_uom_policy()

    def before_submit(self):
        if not self.items:
            frappe.throw(
                _(
                    "No items to convert. Click the <b>Analyze</b> button "
                    "first to preview affected items."
                )
            )

        # Re-run the analysis so we're working with the latest state.
        # Items may have gained transactions since the user clicked Analyze.
        self._refresh_analysis()

    def on_submit(self):
        execute_conversion(self)

    def on_cancel(self):
        note = "\n--- Cancelled by {} ---\nNo conversions were reversed.".format(
            frappe.session.user
        )
        self.db_set(
            "conversion_log",
            (self.conversion_log or "") + note,
        )

    # ------------------------------------------------------------------
    # Whitelisted methods
    # ------------------------------------------------------------------

    @frappe.whitelist()
    def analyze(self):
        """Populate the Affected Items table with a fresh analysis.

        Called from the client-side Analyze button.
        """
        self._validate_uom_different()
        
        if self.selection_mode == "Single Item":
            if not self.item_code:
                frappe.throw(_("Item Code is mandatory for Single Item selection mode."))
            self._detect_item_type()
            self._validate_variant_uom_policy()

        self.set("items", [])

        analysis = analyze_conversion(self)
        for row_data in analysis:
            self.append("items", row_data)

        # Aggregate values from the list
        self.total_items = len(analysis)
        if analysis:
            has_txn = any(row["has_transactions"] for row in analysis)
            has_open = any(row["has_open_quantities"] for row in analysis)
            self.has_transactions = 1 if has_txn else 0
            self.has_open_quantities = 1 if has_open else 0
            
            strategies = set(row["strategy"] for row in analysis)
            if len(strategies) > 1:
                self.conversion_strategy = "Mixed"
            else:
                self.conversion_strategy = list(strategies)[0]
        else:
            self.has_transactions = 0
            self.has_open_quantities = 0
            self.conversion_strategy = ""

        self.save()
        return analysis

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_uom_different(self):
        if self.new_stock_uom and self.current_stock_uom:
            if self.new_stock_uom == self.current_stock_uom:
                frappe.throw(
                    _("New Stock UOM must be different from the current Stock UOM ({0}).").format(
                        frappe.bold(self.current_stock_uom)
                    )
                )

    def _detect_item_type(self):
        """Auto-detect whether the item is Standard / Template / Variant."""
        if not self.item_code:
            return

        has_variants, variant_of = frappe.db.get_value(
            "Item", self.item_code, ["has_variants", "variant_of"]
        ) or (0, None)

        if has_variants:
            self.item_type = "Template"
        elif variant_of:
            self.item_type = "Variant"
            self.variant_of = variant_of
        else:
            self.item_type = "Standard"

    def _validate_variant_uom_policy(self):
        """Prevent converting a variant's UOM when the setting disallows it."""
        if self.item_type != "Variant":
            return

        allow_different_uom = frappe.db.get_single_value(
            "Item Variant Settings", "allow_different_uom"
        )
        if not allow_different_uom:
            frappe.throw(
                _(
                    "Item Variant Settings does not allow different UOMs on "
                    "variants. Change the UOM on the template item <b>{0}</b> "
                    "instead, which will cascade to all variants."
                ).format(self.variant_of)
            )

    def _refresh_analysis(self):
        """Re-run analysis in-place before submit to catch stale data."""
        analysis = analyze_conversion(self)
        self.set("items", [])
        for row_data in analysis:
            self.append("items", row_data)

        self.total_items = len(analysis)
        if analysis:
            has_txn = any(row["has_transactions"] for row in analysis)
            has_open = any(row["has_open_quantities"] for row in analysis)
            self.has_transactions = 1 if has_txn else 0
            self.has_open_quantities = 1 if has_open else 0
            
            strategies = set(row["strategy"] for row in analysis)
            if len(strategies) > 1:
                self.conversion_strategy = "Mixed"
            else:
                self.conversion_strategy = list(strategies)[0]
        else:
            self.has_transactions = 0
            self.has_open_quantities = 0
            self.conversion_strategy = ""
