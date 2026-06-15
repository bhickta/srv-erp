from __future__ import annotations

import secrets
from dataclasses import dataclass

import frappe
from frappe import _
from frappe.utils import cint, nowdate


PACKAGE_BARCODE_PREFIX = "PBC"


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
		for _ in range(10):
			barcode = f"{PACKAGE_BARCODE_PREFIX}-{nowdate().replace('-', '')}-{secrets.token_hex(5).upper()}"
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
		if not self.rows:
			return

		self.validate_duplicate_scans()
		self.validate_master_data()

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


def get_item_uom_options(item_code: str) -> list[str]:
	item = frappe.get_cached_doc("Item", item_code)
	uoms = [row.uom for row in item.get("uoms") if row.uom]
	if item.stock_uom and item.stock_uom not in uoms:
		uoms.insert(0, item.stock_uom)
	return uoms


def get_item_uom_details(item_code: str) -> dict:
	item = frappe.get_cached_doc("Item", item_code)
	return {
		"stock_uom": item.stock_uom,
		"uoms": get_item_uom_options(item_code),
	}


def validate_stock_transaction(doc, method=None) -> None:
	if doc.doctype in {"Stock Entry", "Delivery Note"}:
		PackageBarcodeTransactionValidator(doc).validate()
