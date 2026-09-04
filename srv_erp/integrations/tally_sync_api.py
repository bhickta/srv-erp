"""Backward-compatible SRV API around its connector-owned flow base."""

import json

import frappe
from frappe import _
from frappe.utils import cint

from express_tally.framework.engine import make_context

from srv_erp.integrations.tally_flow import SRVSalesDocumentsToTally


SCHEMA_VERSION = 1
ALLOWED_ROLES = {"Tally Sync User", "Accounts Manager", "System Manager"}
SOURCE_DOCTYPES = {
	"Sales Order": {"table": "tabSales Order", "date_field": "transaction_date"},
	"Delivery Note": {"table": "tabDelivery Note", "date_field": "posting_date"},
}


def _flow():
	return SRVSalesDocumentsToTally()


def _require_bridge_access():
	_flow().authorize("legacy_api")


def _validate_target(target_id, tally_company):
	context = make_context("validation", target_id, tally_company)
	return context.target_id, context.tally_company


# Private wrappers keep older imports working while implementation lives in the connector.
def _clean_company_suffix(value, company_abbr):
	return _flow().mapper.clean_company_suffix(value, company_abbr)


def _source_hash(payload):
	return _flow().mapper.source_hash(payload)


def _item_group_masters(group_names):
	return _flow().mapper.item_group_masters(group_names)


def _previous_tally_voucher_id(source_doctype, source_name, target_id):
	return _flow().sync_log.previous_target_reference(source_doctype, source_name, target_id)


def _serialize_document(document, company_details, target_id):
	return _flow().mapper.map_document(document, company_details, target_id)


def _unsynced_document_names(
	source_doctype,
	company,
	target_id,
	limit,
	from_date=None,
	to_date=None,
):
	return [
		name
		for _, _, name in _flow().sync_log.pending_references(
			company,
			target_id,
			limit,
			from_date=from_date,
			to_date=to_date,
			source_doctypes=(source_doctype,),
		)
	]


def _get_unsynced_documents(company, target_id, limit, from_date, to_date, source_doctypes):
	return _flow().sync_log.pending_references(
		company,
		target_id,
		limit,
		from_date=from_date,
		to_date=to_date,
		source_doctypes=source_doctypes,
	)


def _context(company, target_id, tally_company, from_date=None, to_date=None):
	try:
		return make_context(company, target_id, tally_company, from_date, to_date)
	except ValueError as exc:
		frappe.throw(_(str(exc)))


def _pull(company, target_id, tally_company, limit, from_date, to_date, source_doctypes):
	flow = _flow()
	flow.authorize("pull")
	context = _context(company, target_id, tally_company, from_date, to_date)
	try:
		return context, flow.pull_sources(context, min(max(cint(limit), 1), 100), source_doctypes)
	except ValueError as exc:
		frappe.throw(_(str(exc)))


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
	context, orders = _pull(
		company, target_id, tally_company, limit, from_date, to_date, ("Sales Order",)
	)
	return {
		"schema_version": SCHEMA_VERSION,
		"target_id": context.target_id,
		"tally_company": context.tally_company,
		"company": context.company,
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
	"""Return Sales Orders and Delivery Notes as Sales-voucher inputs."""
	context, documents = _pull(
		company, target_id, tally_company, limit, from_date, to_date, tuple(SOURCE_DOCTYPES)
	)
	return {
		"schema_version": SCHEMA_VERSION,
		"target_id": context.target_id,
		"tally_company": context.tally_company,
		"company": context.company,
		"documents": documents,
	}


def _parse_results(results):
	if isinstance(results, str):
		results = json.loads(results)
	if not isinstance(results, list) or len(results) > 100:
		frappe.throw(_("results must be a JSON array containing at most 100 entries"))
	return results


@frappe.whitelist(methods=["POST"])
def acknowledge_sales_orders(target_id, tally_company, results, company=None):
	"""Backward-compatible acknowledgement endpoint for Sales Orders only."""
	parsed_results = _parse_results(results)
	for result in parsed_results:
		result.setdefault("source_doctype", "Sales Order")
	return acknowledge_sales_documents(target_id, tally_company, parsed_results, company)


@frappe.whitelist(methods=["POST"])
def acknowledge_sales_documents(target_id, tally_company, results, company=None):
	"""Record results through the connector's idempotent shared sync log."""
	flow = _flow()
	flow.authorize("acknowledge")
	parsed_results = _parse_results(results)
	if not company:
		companies = {
			frappe.db.get_value(result.get("source_doctype"), result.get("source_name"), "company")
			for result in parsed_results
			if result.get("source_doctype") in SOURCE_DOCTYPES and result.get("source_name")
		}
		companies.discard(None)
		if len(companies) != 1:
			frappe.throw(_("A single ERPNext company is required for this acknowledgement"))
		company = companies.pop()
	context = _context(company, target_id, tally_company)
	try:
		return flow.acknowledge(context, parsed_results)
	except ValueError as exc:
		frappe.throw(_(str(exc)))


@frappe.whitelist()
def get_sync_status(company, target_id, tally_company):
	flow = _flow()
	flow.authorize("status")
	return flow.status(_context(company, target_id, tally_company))
