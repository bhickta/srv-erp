"""Authenticated pull/ack API for the standalone Tally bridge.

This module deliberately does not use ``tally_export``.  It exposes a stable,
versioned JSON contract and keeps an immutable acknowledgement log so retries
are safe and one Tally target cannot hide work from another target.
"""

import hashlib
import json
import re

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime


SCHEMA_VERSION = 1
ALLOWED_ROLES = {"Tally Sync User", "Accounts Manager", "System Manager"}
TARGET_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,139}$")
SOURCE_DOCTYPES = {
	"Sales Order": {"table": "tabSales Order", "date_field": "transaction_date"},
	"Delivery Note": {"table": "tabDelivery Note", "date_field": "posting_date"},
}


def _require_bridge_access():
	if frappe.session.user == "Guest" or not ALLOWED_ROLES.intersection(frappe.get_roles()):
		frappe.throw(_("Tally bridge access is not permitted"), frappe.PermissionError)


def _validate_target(target_id, tally_company):
	target_id = (target_id or "").strip()
	tally_company = (tally_company or "").strip()
	if not TARGET_ID_PATTERN.fullmatch(target_id):
		frappe.throw(_("Target ID may contain letters, numbers, dot, colon, underscore and hyphen"))
	if not tally_company or len(tally_company) > 140:
		frappe.throw(_("A valid Tally company is required"))
	return target_id, tally_company


def _clean_company_suffix(value, company_abbr):
	value = (value or "").strip()
	if company_abbr:
		value = re.sub(rf"\s+-\s+{re.escape(company_abbr)}$", "", value).strip()
	return value


def _source_hash(payload):
	content = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
	return hashlib.sha256(content.encode()).hexdigest()


def _item_group_masters(group_names):
	masters = {}
	remaining = list(filter(None, group_names))
	while remaining:
		name = remaining.pop()
		if name == "All Item Groups" or name in masters:
			continue
		parent = frappe.db.get_value("Item Group", name, "parent_item_group") or ""
		masters[name] = {
			"name": name,
			"parent": "" if parent == "All Item Groups" else parent,
		}
		if parent and parent != "All Item Groups":
			remaining.append(parent)
	ordered = []
	visited = set()

	def add_with_parent(name):
		if name in visited or name not in masters:
			return
		parent = masters[name]["parent"]
		add_with_parent(parent)
		visited.add(name)
		ordered.append(masters[name])

	for name in sorted(masters):
		add_with_parent(name)
	return ordered


def _previous_tally_voucher_id(source_doctype, source_name, target_id):
	return frappe.db.get_value(
		"Tally Sync Log",
		{
			"source_doctype": source_doctype,
			"source_name": source_name,
			"target_id": target_id,
			"status": "Success",
		},
		"tally_voucher_id",
		order_by="creation desc",
	) or ""


def _serialize_document(document, company_details, target_id):
	abbr = company_details.abbr
	item_codes = {row.item_code for row in document.items if row.item_code}
	item_details = {
		row.name: row
		for row in frappe.get_all(
			"Item",
			filters={"name": ["in", sorted(item_codes)]},
			fields=["name", "item_name", "description", "item_group", "stock_uom", "gst_hsn_code"],
		)
	}

	items = []
	transaction_date = document.get("transaction_date") or document.get("posting_date")
	delivery_date = document.get("delivery_date") or transaction_date
	for row in document.items:
		item = item_details.get(row.item_code) or frappe._dict()
		stock_qty = flt(row.stock_qty) or flt(row.qty)
		items.append(
			{
				"item_code": row.item_code,
				"item_name": item.get("item_name") or row.item_name or row.item_code,
				"description": item.get("description") or row.description or "",
				"item_group": item.get("item_group") or row.item_group or "",
				"hsn_code": item.get("gst_hsn_code") or row.get("gst_hsn_code") or "",
				"stock_uom": item.get("stock_uom") or row.stock_uom or row.uom,
				"stock_qty": stock_qty,
				"rate": flt(row.base_net_amount) / stock_qty if stock_qty else 0,
				"amount": flt(row.base_net_amount),
				"warehouse": _clean_company_suffix(row.warehouse, abbr),
				"delivery_date": str(row.get("delivery_date") or delivery_date),
			}
		)

	party = document.customer_name or document.customer
	taxes = [
		{
			"ledger": _clean_company_suffix(row.account_head, abbr),
			"amount": flt(row.base_tax_amount_after_discount_amount),
		}
		for row in document.taxes
		if row.account_head and flt(row.base_tax_amount_after_discount_amount)
	]
	round_off_ledger = _clean_company_suffix(company_details.round_off_account, abbr)
	linked_sales_orders = [
		row.get("against_sales_order") for row in document.items if row.get("against_sales_order")
	]
	rounding_adjustment = flt(document.base_rounding_adjustment)
	grand_total = (
		flt(document.base_rounded_total)
		if rounding_adjustment and not document.get("disable_rounded_total")
		else flt(document.base_grand_total)
	)
	previous_tally_voucher_id = _previous_tally_voucher_id(
		document.doctype, document.name, target_id
	)
	payload = {
		"source_doctype": document.doctype,
		"name": document.name,
		"modified": str(document.modified),
		"operation": "Alter" if previous_tally_voucher_id else "Create",
		"tally_voucher_id": previous_tally_voucher_id,
		"transaction_date": str(transaction_date),
		"delivery_date": str(delivery_date),
		"customer": {
			"id": document.customer,
			"name": party,
			"gstin": document.get("billing_address_gstin") or document.get("tax_id") or "",
			"country": company_details.country or "",
		},
		"currency": document.currency,
		"reference": document.get("po_no") or next(iter(linked_sales_orders), None) or document.name,
		"narration": document.get("custom_remarks") or document.get("terms") or "",
		"net_total": flt(document.base_net_total),
		"grand_total": grand_total,
		"rounding_adjustment": rounding_adjustment,
		"sales_ledger": _clean_company_suffix(company_details.default_income_account, abbr) or "Sales",
		"round_off_ledger": round_off_ledger or "Round Off",
		"taxes": taxes,
		"items": items,
		"masters": {
			"item_groups": _item_group_masters({row["item_group"] for row in items}),
			"units": sorted({row["stock_uom"] for row in items if row["stock_uom"]}),
			"warehouses": sorted({row["warehouse"] for row in items if row["warehouse"]}),
		},
	}
	payload["source_hash"] = _source_hash(payload)
	return payload


def _unsynced_document_names(
	source_doctype,
	company,
	target_id,
	limit,
	from_date=None,
	to_date=None,
):
	config = SOURCE_DOCTYPES[source_doctype]
	table = config["table"]
	date_field = config["date_field"]
	conditions = ["source.company = %(company)s", "source.docstatus = 1", "log.name IS NULL"]
	values = {
		"company": company,
		"target_id": target_id,
		"source_doctype": source_doctype,
		"limit": limit,
	}
	if from_date:
		conditions.append(f"source.{date_field} >= %(from_date)s")
		values["from_date"] = from_date
	if to_date:
		conditions.append(f"source.{date_field} <= %(to_date)s")
		values["to_date"] = to_date
	return frappe.db.sql_list(
		f"""
			SELECT source.name
			FROM `{table}` source
			LEFT JOIN `tabTally Sync Log` log
				ON log.source_doctype = %(source_doctype)s
				AND log.source_name = source.name
				AND log.source_modified = source.modified
			AND log.target_id = %(target_id)s
			AND log.status = 'Success'
		WHERE {' AND '.join(conditions)}
			ORDER BY source.{date_field}, source.name
		LIMIT %(limit)s
		""",
		values,
	)


def _get_unsynced_documents(company, target_id, limit, from_date, to_date, source_doctypes):
	refs = []
	for source_doctype in source_doctypes:
		date_field = SOURCE_DOCTYPES[source_doctype]["date_field"]
		for name in _unsynced_document_names(
			source_doctype,
			company,
			target_id,
			limit,
			from_date,
			to_date,
		):
			refs.append(
				(
					str(frappe.db.get_value(source_doctype, name, date_field)),
					source_doctype,
					name,
				)
			)
	return refs


@frappe.whitelist()
def get_unsynced_sales_orders(
	company,
	target_id,
	tally_company,
	limit=20,
	from_date=None,
	to_date=None,
):
	"""Return submitted Sales Orders not acknowledged at their current version."""
	_require_bridge_access()
	target_id, tally_company = _validate_target(target_id, tally_company)
	if not frappe.db.exists("Company", company):
		frappe.throw(_("Company {0} does not exist").format(frappe.bold(company)))
	limit = min(max(cint(limit), 1), 100)
	company_details = frappe.db.get_value(
		"Company",
		company,
		["abbr", "country", "default_income_account", "round_off_account"],
		as_dict=True,
	)
	orders = [
		_serialize_document(frappe.get_doc(source_doctype, name), company_details, target_id)
		for _, source_doctype, name in sorted(
			_get_unsynced_documents(
				company, target_id, limit, from_date, to_date, ("Sales Order",)
			)
		)[:limit]
	]
	return {
		"schema_version": SCHEMA_VERSION,
		"target_id": target_id,
		"tally_company": tally_company,
		"company": company,
		"orders": orders,
	}


@frappe.whitelist()
def get_unsynced_sales_documents(
	company,
	target_id,
	tally_company,
	limit=20,
	from_date=None,
	to_date=None,
):
	"""Return unsynced Sales Orders and Delivery Notes as Sales-voucher inputs."""
	_require_bridge_access()
	target_id, tally_company = _validate_target(target_id, tally_company)
	if not frappe.db.exists("Company", company):
		frappe.throw(_("Company {0} does not exist").format(frappe.bold(company)))
	limit = min(max(cint(limit), 1), 100)
	company_details = frappe.db.get_value(
		"Company",
		company,
		["abbr", "country", "default_income_account", "round_off_account"],
		as_dict=True,
	)
	refs = sorted(
		_get_unsynced_documents(
			company,
			target_id,
			limit,
			from_date,
			to_date,
			tuple(SOURCE_DOCTYPES),
		)
	)[:limit]
	documents = [
		_serialize_document(frappe.get_doc(source_doctype, name), company_details, target_id)
		for _, source_doctype, name in refs
	]
	return {
		"schema_version": SCHEMA_VERSION,
		"target_id": target_id,
		"tally_company": tally_company,
		"company": company,
		"documents": documents,
	}


def _parse_results(results):
	if isinstance(results, str):
		results = json.loads(results)
	if not isinstance(results, list) or len(results) > 100:
		frappe.throw(_("results must be a JSON array containing at most 100 entries"))
	return results


@frappe.whitelist(methods=["POST"])
def acknowledge_sales_orders(target_id, tally_company, results):
	"""Backward-compatible acknowledgement endpoint for Sales Orders only."""
	parsed_results = _parse_results(results)
	for result in parsed_results:
		result.setdefault("source_doctype", "Sales Order")
	return acknowledge_sales_documents(target_id, tally_company, parsed_results)


@frappe.whitelist(methods=["POST"])
def acknowledge_sales_documents(target_id, tally_company, results):
	"""Record per-document bridge results; repeated request IDs are idempotent."""
	_require_bridge_access()
	target_id, tally_company = _validate_target(target_id, tally_company)
	created = 0
	for result in _parse_results(results):
		request_id = str(result.get("request_id") or "").strip()
		if not request_id or len(request_id) > 140:
			frappe.throw(_("Every result requires a valid request_id"))
		if frappe.db.exists("Tally Sync Log", {"request_id": request_id}):
			continue
		status = result.get("status")
		operation = result.get("operation")
		if status not in ("Success", "Failed") or operation not in ("Create", "Alter", "Cancel"):
			frappe.throw(_("Invalid sync status or operation"))
		source_doctype = str(result.get("source_doctype") or "").strip()
		if source_doctype not in SOURCE_DOCTYPES:
			frappe.throw(_("Invalid source DocType"))
		source_name = str(result.get("source_name") or "").strip()
		if not frappe.db.exists(source_doctype, source_name):
			frappe.throw(
				_("{0} {1} does not exist").format(source_doctype, frappe.bold(source_name))
			)
		frappe.get_doc(
			{
				"doctype": "Tally Sync Log",
				"request_id": request_id,
				"status": status,
				"operation": operation,
				"source_doctype": source_doctype,
				"source_name": source_name,
				"source_modified": result.get("source_modified"),
				"source_hash": result.get("source_hash"),
				"target_id": target_id,
				"tally_company": tally_company,
				"tally_voucher_id": result.get("tally_voucher_id"),
				"synced_on": now_datetime(),
				"error": str(result.get("error") or "")[:4000],
			}
		).insert(ignore_permissions=True)
		created += 1
	return {"accepted": created}


@frappe.whitelist()
def get_sync_status(company, target_id, tally_company):
	_require_bridge_access()
	target_id, tally_company = _validate_target(target_id, tally_company)
	pending_by_doctype = {
		source_doctype: len(
			_unsynced_document_names(source_doctype, company, target_id, 100000)
		)
		for source_doctype in SOURCE_DOCTYPES
	}
	return {
		"target_id": target_id,
		"tally_company": tally_company,
		"pending": sum(pending_by_doctype.values()),
		"pending_by_doctype": pending_by_doctype,
		"successful": frappe.db.count("Tally Sync Log", {"target_id": target_id, "status": "Success"}),
		"failed": frappe.db.count("Tally Sync Log", {"target_id": target_id, "status": "Failed"}),
	}
