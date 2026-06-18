import frappe
from frappe.utils.xlsxutils import build_xlsx_response

from srv_erp.package_barcode.service import (
	PackageBarcodeGenerator,
	PackageBarcodeResolver,
	get_item_uom_details,
)


@frappe.whitelist()
def get_item_uoms(item_code: str) -> dict:
	return get_item_uom_details(item_code)


@frappe.whitelist()
def generate_package_barcodes(item_code: str, uom: str, no_of_barcodes: int) -> dict:
	return PackageBarcodeGenerator(item_code=item_code, uom=uom, no_of_barcodes=no_of_barcodes).generate()


@frappe.whitelist()
def scan_package_barcode(search_value: str, ctx: dict | str | None = None) -> dict:
	if not frappe.db.exists("Package Barcode", {"barcode": (search_value or "").strip()}):
		from erpnext.stock.utils import scan_barcode

		return scan_barcode(search_value, ctx)

	return PackageBarcodeResolver(search_value).resolve().as_dict()


@frappe.whitelist()
def download_package_barcode_batch(batch: str) -> None:
	rows = [["Item Code", "Barcode", "UOM", "Package Barcode", "Status"]]
	for row in frappe.get_all(
		"Package Barcode",
		filters={"generation_batch": batch},
		fields=["item_code", "barcode", "uom", "name", "status"],
		order_by="creation asc",
	):
		rows.append([row.item_code, row.barcode, row.uom, row.name, row.status])

	build_xlsx_response(rows, f"package_barcodes_{batch}")


@frappe.whitelist()
def download_package_barcodes(names: list[str] | str) -> None:
	names = frappe.parse_json(names) if isinstance(names, str) else names
	rows = [["Item Code", "Barcode", "UOM", "Package Barcode", "Status", "Generation Batch"]]
	if names:
		for row in frappe.get_all(
			"Package Barcode",
			filters={"name": ("in", names)},
			fields=["item_code", "barcode", "uom", "name", "status", "generation_batch"],
			order_by="creation asc",
		):
			rows.append([row.item_code, row.barcode, row.uom, row.name, row.status, row.generation_batch])

	build_xlsx_response(rows, "package_barcodes_selected")


@frappe.whitelist()
def download_package_barcode_batches(batches: list[str] | str) -> None:
	batches = frappe.parse_json(batches) if isinstance(batches, str) else batches
	rows = [["Batch", "Item Code", "Barcode", "UOM", "Package Barcode", "Status"]]
	if batches:
		for row in frappe.get_all(
			"Package Barcode",
			filters={"generation_batch": ("in", batches)},
			fields=["generation_batch", "item_code", "barcode", "uom", "name", "status"],
			order_by="generation_batch asc, creation asc",
		):
			rows.append([row.generation_batch, row.item_code, row.barcode, row.uom, row.name, row.status])

	build_xlsx_response(rows, "package_barcodes_by_batch")
