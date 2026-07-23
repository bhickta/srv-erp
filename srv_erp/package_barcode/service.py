from __future__ import annotations

from dataclasses import dataclass

import frappe
from frappe import _
from frappe.model.naming import make_autoname
from frappe.utils import cint, flt


DEFAULT_BARCODE_NAMING_SERIES = "PBC-.YYYY.-.#####"
QTY_RULE_DEFAULT = "Default"
QTY_RULE_ALLOW_MANUAL = "Allow Manual Qty"
QTY_RULE_FORCE_BARCODE = "Force Barcode Only"


@dataclass(frozen=True)
class PackageBarcodePayload:
	package_barcode: str
	barcode: str
	item_code: str
	uom: str
	qty: int = 1

	def as_dict(self) -> dict:
		return {
			"package_barcode": self.package_barcode,
			"barcode": self.barcode,
			"item_code": self.item_code,
			"uom": self.uom,
			"qty": self.qty,
		}


class PackageBarcodeError(frappe.ValidationError):
	pass


class PackageBarcodeGenerator:
	def __init__(self, item_code: str, uom: str, no_of_barcodes: int):
		self.item_code = item_code
		self.uom = uom
		self.no_of_barcodes = cint(no_of_barcodes)

	def generate(self) -> frappe._dict:
		self.validate()

		batch = frappe.get_doc(
			{
				"doctype": "Package Barcode Batch",
				"item_code": self.item_code,
				"uom": self.uom,
				"no_of_barcodes": self.no_of_barcodes,
				"generated_count": 0,
				"status": "Draft",
			}
		).insert(ignore_permissions=True)

		records = []
		for _ in range(self.no_of_barcodes):
			barcode = self.make_unique_barcode()
			doc = frappe.get_doc(
				{
					"doctype": "Package Barcode",
					"barcode": barcode,
					"item_code": self.item_code,
					"uom": self.uom,
					"generation_batch": batch.name,
					"status": "Active",
				}
			).insert(ignore_permissions=True)
			records.append(doc)

		batch.db_set("generated_count", len(records), update_modified=False)
		batch.db_set("status", "Completed", update_modified=False)

		return frappe._dict(
			{
				"batch": batch.name,
				"generated_count": len(records),
				"barcodes": [record.name for record in records],
			}
		)

	def validate(self) -> None:
		if not self.item_code:
			frappe.throw(_("Item Code is required."), PackageBarcodeError)
		if not self.uom:
			frappe.throw(_("UOM is required."), PackageBarcodeError)
		if self.no_of_barcodes <= 0:
			frappe.throw(_("No. of Barcodes must be greater than zero."), PackageBarcodeError)

		item = frappe.db.get_value(
			"Item",
			self.item_code,
			["name", "disabled", "is_stock_item", "stock_uom"],
			as_dict=True,
		)
		if not item:
			frappe.throw(_("Item {0} does not exist.").format(frappe.bold(self.item_code)), PackageBarcodeError)
		if item.disabled:
			frappe.throw(_("Item {0} is disabled.").format(frappe.bold(self.item_code)), PackageBarcodeError)
		if not item.is_stock_item:
			frappe.throw(_("Item {0} is not a stock item.").format(frappe.bold(self.item_code)), PackageBarcodeError)

		if self.uom not in get_item_uom_options(self.item_code):
			frappe.throw(
				_("UOM {0} is not configured for Item {1}.").format(
					frappe.bold(self.uom), frappe.bold(self.item_code)
				),
				PackageBarcodeError,
			)

	def make_unique_barcode(self) -> str:
		series = get_barcode_naming_series()
		for _ in range(10):
			barcode = make_autoname(series)
			if not frappe.db.exists("Package Barcode", {"barcode": barcode}):
				return barcode

		frappe.throw(_("Unable to generate a unique package barcode. Please try again."), PackageBarcodeError)


class PackageBarcodeResolver:
	def __init__(self, barcode: str):
		self.barcode = (barcode or "").strip()

	def resolve(self) -> PackageBarcodePayload:
		if not self.barcode:
			frappe.throw(_("Barcode is required."), PackageBarcodeError)

		doc = frappe.db.get_value(
			"Package Barcode",
			{"barcode": self.barcode},
			["name", "barcode", "item_code", "uom", "status"],
			as_dict=True,
		)
		if not doc:
			frappe.throw(_("Package Barcode {0} was not found.").format(frappe.bold(self.barcode)), PackageBarcodeError)
		if doc.status != "Active":
			frappe.throw(
				_("Package Barcode {0} is {1}.").format(frappe.bold(self.barcode), frappe.bold(doc.status)),
				PackageBarcodeError,
			)

		return PackageBarcodePayload(
			package_barcode=doc.name,
			barcode=doc.barcode,
			item_code=doc.item_code,
			uom=doc.uom,
		)


class PackageBarcodeTransactionValidator:
	def __init__(self, doc):
		self.doc = doc
		self.rows = list(doc.get("package_barcodes") or [])

	def validate(self) -> None:
		self.validate_duplicate_scans()
		self.validate_master_data()
		self.sync_stock_reconciliation_package_uom_quantities()
		self.validate_barcode_only_quantities()

	def validate_duplicate_scans(self) -> None:
		seen = set()
		duplicates = set()
		for row in self.rows:
			key = row.package_barcode or row.barcode
			if not key:
				continue
			if key in seen:
				duplicates.add(key)
			seen.add(key)

		if duplicates:
			frappe.throw(
				_("Package Barcode(s) already scanned in this document: {0}").format(", ".join(sorted(duplicates))),
				PackageBarcodeError,
			)

	def validate_master_data(self) -> None:
		package_names = [row.package_barcode for row in self.rows if row.package_barcode]
		if not package_names:
			return

		masters = {
			row.name: row
			for row in frappe.get_all(
				"Package Barcode",
				filters={"name": ("in", package_names)},
				fields=["name", "barcode", "item_code", "uom", "status"],
			)
		}

		for row in self.rows:
			if not row.package_barcode:
				frappe.throw(_("Row {0}: Package Barcode is required.").format(row.idx), PackageBarcodeError)

			master = masters.get(row.package_barcode)
			if not master:
				frappe.throw(
					_("Row {0}: Package Barcode {1} does not exist.").format(
						row.idx, frappe.bold(row.package_barcode)
					),
					PackageBarcodeError,
				)
			if master.status != "Active":
				frappe.throw(
					_("Row {0}: Package Barcode {1} is {2}.").format(
						row.idx, frappe.bold(row.package_barcode), frappe.bold(master.status)
					),
					PackageBarcodeError,
				)
			if row.barcode and row.barcode != master.barcode:
				frappe.throw(_("Row {0}: Barcode does not match the Package Barcode master.").format(row.idx))
			if row.item_code != master.item_code or row.uom != master.uom:
				frappe.throw(
					_("Row {0}: Item/UOM does not match the Package Barcode master.").format(row.idx),
					PackageBarcodeError,
				)

	def validate_barcode_only_quantities(self) -> None:
		barcode_only_items = get_barcode_only_items(self.doc)
		if not barcode_only_items:
			return

		if self.doc.doctype == "Stock Reconciliation":
			scanned_qty = get_scanned_stock_qty_by_item(self.rows)
		else:
			scanned_qty = get_scanned_qty_by_item(self.rows)
		quantity_field = get_transaction_quantity_field(self.doc.doctype)
		item_rows = list(self.doc.get("items") or [])
		mismatches = []

		if self.doc.doctype == "Stock Reconciliation":
			row_qty_by_item = get_transaction_qty_by_item(item_rows, quantity_field)
			for item_code in barcode_only_items:
				row_qty = row_qty_by_item.get(item_code, 0)
				expected_qty = scanned_qty.get(item_code, 0)
				if not quantities_match(row_qty, expected_qty):
					mismatches.append(f"{item_code}: {row_qty} != {expected_qty}")
		else:
			for row in item_rows:
				if row.item_code not in barcode_only_items:
					continue

				row_qty = cint(row.get(quantity_field))
				expected_qty = scanned_qty.get(row.item_code, 0)
				if row_qty != expected_qty:
					mismatches.append(f"{row.item_code}: {row_qty} != {expected_qty}")

		if mismatches:
			frappe.throw(
				_(
					"Quantity can only be entered through Package Barcode scans for these item(s): {0}"
				).format(", ".join(mismatches)),
				PackageBarcodeError,
			)

	def sync_stock_reconciliation_package_uom_quantities(self) -> None:
		if self.doc.doctype != "Stock Reconciliation":
			return

		for row in self.doc.get("items") or []:
			if not row.item_code or not row.get("package_uom"):
				continue

			conversion_factor = get_item_uom_conversion_factor(row.item_code, row.package_uom)
			package_qty = flt(row.get("package_qty"))
			qty_precision = get_row_precision(row, "qty")
			row_qty = flt(row.get("qty"), qty_precision)

			row.package_conversion_factor = conversion_factor
			if package_qty:
				row.qty = flt(package_qty * conversion_factor, qty_precision)
			elif row_qty:
				row.package_qty = flt(row_qty / conversion_factor, get_row_precision(row, "package_qty"))


def get_barcode_naming_series() -> str:
	return (
		frappe.db.get_single_value("Barcode Settings", "package_barcode_naming_series")
		or DEFAULT_BARCODE_NAMING_SERIES
	)


def get_default_qty_entry_rule() -> str:
	return (
		frappe.db.get_single_value("Barcode Settings", "package_barcode_default_qty_entry_rule")
		or QTY_RULE_ALLOW_MANUAL
	)


def get_item_qty_entry_rules(item_codes: list[str]) -> dict[str, str]:
	if not item_codes:
		return {}

	return {
		row.name: row.package_barcode_qty_entry_rule
		for row in frappe.get_all(
			"Item",
			filters={"name": ("in", item_codes)},
			fields=["name", "package_barcode_qty_entry_rule"],
		)
	}


def get_effective_qty_entry_rule(item_code: str, item_rules: dict[str, str], default_rule: str) -> str:
	item_rule = item_rules.get(item_code)
	if item_rule and item_rule != QTY_RULE_DEFAULT:
		return item_rule
	return default_rule


def get_barcode_only_items(doc) -> set[str]:
	item_codes = sorted({row.item_code for row in doc.get("items") or [] if row.item_code})
	item_rules = get_item_qty_entry_rules(item_codes)
	default_rule = get_default_qty_entry_rule()
	return {
		item_code
		for item_code in item_codes
		if get_effective_qty_entry_rule(item_code, item_rules, default_rule) == QTY_RULE_FORCE_BARCODE
	}


def get_scanned_qty_by_item(rows) -> dict[str, int]:
	scanned_qty: dict[str, int] = {}
	for row in rows:
		if row.item_code:
			scanned_qty[row.item_code] = scanned_qty.get(row.item_code, 0) + 1
	return scanned_qty


def get_scanned_stock_qty_by_item(rows) -> dict[str, float]:
	scanned_qty: dict[str, float] = {}
	for row in rows:
		if row.item_code and row.uom:
			conversion_factor = get_item_uom_conversion_factor(row.item_code, row.uom)
			scanned_qty[row.item_code] = scanned_qty.get(row.item_code, 0) + conversion_factor
	return scanned_qty


def get_transaction_qty_by_item(rows, quantity_field: str) -> dict[str, float]:
	qty_by_item: dict[str, float] = {}
	for row in rows:
		if row.item_code:
			qty_by_item[row.item_code] = qty_by_item.get(row.item_code, 0) + flt(row.get(quantity_field))
	return qty_by_item


def quantities_match(left: float, right: float, precision: int = 3) -> bool:
	return flt(left, precision) == flt(right, precision)


def get_transaction_quantity_field(doctype: str) -> str:
	if doctype == "Delivery Note":
		return "qty"
	if doctype == "Stock Entry":
		return "qty"
	return "qty"


def get_item_uom_options(item_code: str) -> list[str]:
	item = frappe.get_cached_doc("Item", item_code)
	uoms = [row.uom for row in item.get("uoms") if row.uom]
	if item.stock_uom and item.stock_uom not in uoms:
		uoms.insert(0, item.stock_uom)
	return uoms


def get_item_uom_conversion_factor(item_code: str, uom: str) -> float:
	item = frappe.get_cached_doc("Item", item_code)
	if uom == item.stock_uom:
		return 1.0

	for row in item.get("uoms"):
		if row.uom == uom:
			return flt(row.conversion_factor)

	frappe.throw(
		_("UOM {0} is not configured for Item {1}.").format(frappe.bold(uom), frappe.bold(item_code)),
		PackageBarcodeError,
	)


def get_row_precision(row, fieldname: str, default: int = 3) -> int:
	if hasattr(row, "precision"):
		return row.precision(fieldname)
	return default


def get_item_uom_details(item_code: str) -> dict:
	item = frappe.get_cached_doc("Item", item_code)
	return {
		"item_code": item.name,
		"item_name": item.item_name,
		"stock_uom": item.stock_uom,
		"uoms": get_item_uom_options(item_code),
		"conversion_factors": {
			uom: get_item_uom_conversion_factor(item_code, uom) for uom in get_item_uom_options(item_code)
		},
	}


def validate_stock_transaction(doc, method=None) -> None:
	if doc.doctype in {"Stock Entry", "Delivery Note", "Stock Reconciliation"}:
		PackageBarcodeTransactionValidator(doc).validate()


def sync_stock_transaction_package_quantities(doc, method=None) -> None:
	if doc.doctype == "Stock Reconciliation":
		PackageBarcodeTransactionValidator(doc).sync_stock_reconciliation_package_uom_quantities()
