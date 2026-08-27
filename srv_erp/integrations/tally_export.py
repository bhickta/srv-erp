"""Export ERPNext masters in TallyPrime 7 native JSON format."""

import json
import re

import frappe
from frappe import _
from frappe.utils import cint, flt, formatdate, getdate


SUPPORTED_MASTER_DOCTYPES = (
	"Account",
	"Customer",
	"Supplier",
	"Cost Center",
	"UOM",
	"Item Group",
	"Warehouse",
	"Item",
)

DEFAULT_ACCOUNT_GROUPS = {
	"Bank": "Bank Accounts",
	"Cash": "Cash-in-Hand",
	"Receivable": "Sundry Debtors",
	"Payable": "Sundry Creditors",
	"Tax": "Duties & Taxes",
	"Stock": "Stock-in-Hand",
	"Fixed Asset": "Fixed Assets",
	"Accumulated Depreciation": "Fixed Assets",
	"Depreciation": "Indirect Expenses",
	"Income Account": "Sales Accounts",
	"Expense Account": "Direct Expenses",
	"Cost of Goods Sold": "Direct Expenses",
	"Chargeable": "Indirect Expenses",
}


def _metadata(object_type, name):
	return {"type": object_type, "name": name, "reservedname": ""}


def _master_payload(messages):
	"""Return masters with the object-level name required by TallyPrime JSON import."""
	normalized_messages = []
	for message in messages:
		message = dict(message)
		metadata = message.get("metadata") or {}
		if metadata.get("name") and not message.get("name"):
			message["name"] = metadata["name"]
		normalized_messages.append(message)

	return {"tallymessage": normalized_messages}


def _voucher_metadata(name):
	return {
		"type": "Voucher",
		"name": name,
		"vchtype": "Sales Order",
		"action": "Create",
		"objview": "Invoice Voucher View",
		"remoteid": f"ERPNext-Sales-Order-{name}",
	}


def _clean_name(value, company_abbr=None):
	value = (value or "").strip()
	if company_abbr:
		value = re.sub(rf"\s+-\s+{re.escape(company_abbr)}$", "", value).strip()
	return value


def _company_abbr(company):
	return frappe.db.get_value("Company", company, "abbr")


def _account_parent(account, by_name, company_abbr):
	parent = by_name.get(account.get("parent_account"))
	if parent and parent.get("parent_account"):
		return _clean_name(parent.get("account_name") or parent.get("name"), company_abbr)
	return DEFAULT_ACCOUNT_GROUPS.get(account.get("account_type")) or {
		"Asset": "Current Assets",
		"Liability": "Current Liabilities",
		"Equity": "Capital Account",
		"Income": "Indirect Incomes",
		"Expense": "Indirect Expenses",
	}.get(account.get("root_type"), "Current Assets")


def _group(name, parent):
	return {
		"metadata": _metadata("Group", name),
		"parent": parent,
		"isbillwiseon": False,
		"iscostcentreson": False,
		"isaddable": True,
		"isrevenue": parent in ("Direct Incomes", "Indirect Incomes", "Sales Accounts"),
		"affectsstock": False,
	}


def _ledger(name, parent, billwise=False, tax_id=None, country=None):
	row = {
		"metadata": _metadata("Ledger", name),
		"parent": parent,
		"isbillwiseon": bool(billwise),
		"iscostcentreson": False,
		"affectsstock": False,
		"isgstapplicable": bool(tax_id),
	}
	if country:
		row["countryofresidence"] = country
	if tax_id:
		row["partygstin"] = tax_id
	return row


def _export_accounts(company, company_abbr, include_disabled=False):
	filters = {"company": company}
	if not include_disabled:
		filters["disabled"] = 0
	accounts = frappe.get_all(
		"Account",
		filters=filters,
		fields=[
			"name", "account_name", "parent_account", "is_group", "root_type",
			"account_type", "account_currency",
		],
		order_by="lft",
	)
	by_name = {row.name: row for row in accounts}
	result = []
	for account in accounts:
		if not account.parent_account:
			continue
		name = _clean_name(account.account_name or account.name, company_abbr)
		parent = _account_parent(account, by_name, company_abbr)
		if account.is_group:
			result.append(_group(name, parent))
		else:
			result.append(
				_ledger(
					name,
					parent,
					billwise=account.account_type in ("Receivable", "Payable"),
				)
			)
	return result


def _export_parties(doctype, parent, company, names=None):
	if doctype == "Customer":
		fields = ["name", "customer_name", "tax_id", "territory"]
		party_name_field = "customer_name"
	else:
		fields = ["name", "supplier_name", "tax_id", "country"]
		party_name_field = "supplier_name"

	result = []
	filters = {"name": ["in", sorted(names)]} if names is not None else None
	for party in frappe.get_all(doctype, filters=filters, fields=fields, order_by="name"):
		name = party.get(party_name_field) or party.name
		country = party.get("country")
		if not country and doctype == "Customer":
			country = frappe.db.get_value("Company", company, "country")
		result.append(_ledger(name, parent, billwise=True, tax_id=party.get("tax_id"), country=country))
	return result


def _export_cost_centers(company, company_abbr):
	rows = frappe.get_all(
		"Cost Center",
		filters={"company": company, "disabled": 0},
		fields=["name", "cost_center_name", "parent_cost_center", "is_group"],
		order_by="lft",
	)
	result = []
	for row in rows:
		if not row.parent_cost_center:
			continue
		name = _clean_name(row.cost_center_name or row.name, company_abbr)
		parent = _clean_name(row.parent_cost_center, company_abbr) or "Primary Cost Category"
		result.append(
			{
				"metadata": _metadata("CostCentre", name),
				"parent": parent,
				"category": "Primary Cost Category",
			}
		)
	return result


def _export_uoms(uoms=None):
	if uoms is None:
		used_uoms = set(
			frappe.get_all(
				"Item",
				filters={"disabled": 0, "is_stock_item": 1},
				pluck="stock_uom",
			)
		)
		used_uoms.update(
			frappe.get_all(
				"UOM Conversion Detail",
				filters={"parenttype": "Item"},
				pluck="uom",
			)
		)
	else:
		used_uoms = set(uoms)
	return [
		{
			"metadata": _metadata("Unit", row.name),
			"originalname": row.name,
			"issimpleunit": True,
			"decimalplaces": str(cint(row.must_be_whole_number == 0) * 3),
		}
		for row in frappe.get_all(
			"UOM",
			filters={"name": ["in", sorted(filter(None, used_uoms))]},
			fields=["name", "must_be_whole_number"],
			order_by="name",
		)
	]


def _ancestor_names(rows, requested_names, parent_field, root_name=None):
	by_name = {row.name: row for row in rows}
	result = set()
	remaining = list(filter(None, requested_names))
	while remaining:
		name = remaining.pop()
		if name == root_name or name in result:
			continue
		result.add(name)
		row = by_name.get(name)
		if row and row.get(parent_field):
			remaining.append(row.get(parent_field))
	return result


def _export_item_groups(names=None):
	rows = frappe.get_all(
		"Item Group",
		fields=["name", "parent_item_group", "is_group"],
		order_by="lft",
	)
	if names is not None:
		required_names = _ancestor_names(rows, names, "parent_item_group", "All Item Groups")
		rows = [row for row in rows if row.name in required_names]
	return [
		{
			"metadata": _metadata("StockGroup", row.name),
			"parent": row.parent_item_group if row.parent_item_group != "All Item Groups" else "",
			"shouldquantitiesbeadded": True,
		}
		for row in rows
		if row.name != "All Item Groups"
	]


def _export_warehouses(company, company_abbr, names=None):
	filters = {"company": company}
	if names is None:
		filters["disabled"] = 0
	rows = frappe.get_all(
		"Warehouse",
		filters=filters,
		fields=["name", "warehouse_name", "parent_warehouse", "is_group"],
		order_by="lft",
	)
	if names is not None:
		required_names = _ancestor_names(rows, names, "parent_warehouse")
		rows = [row for row in rows if row.name in required_names]
	return [
		{
			"metadata": _metadata("Godown", _clean_name(row.warehouse_name or row.name, company_abbr)),
			"parent": _clean_name(row.parent_warehouse, company_abbr),
		}
		for row in rows
	]


def _export_items(item_codes=None):
	filters = (
		{"name": ["in", sorted(item_codes)]}
		if item_codes is not None
		else {"disabled": 0, "is_stock_item": 1}
	)
	rows = frappe.get_all(
		"Item",
		filters=filters,
		fields=["name", "item_name", "item_group", "stock_uom", "gst_hsn_code", "description"],
		order_by="name",
	)
	result = []
	for row in rows:
		item = {
			"metadata": _metadata("StockItem", row.name),
			"parent": row.item_group,
			"baseunits": row.stock_uom,
			"description": row.description or row.item_name,
			"isbatchwiseon": False,
			"isgodownon": True,
		}
		if row.gst_hsn_code:
			item["gstapplicable"] = "Applicable"
			item["hsncode"] = row.gst_hsn_code
		result.append(item)
	return result


def build_master_payload(company, doctypes=None):
	"""Return a TallyPrime native JSON-compatible master payload."""
	if not frappe.db.exists("Company", company):
		frappe.throw(_("Company {0} does not exist").format(frappe.bold(company)))

	doctypes = set(doctypes or SUPPORTED_MASTER_DOCTYPES)
	unsupported = doctypes.difference(SUPPORTED_MASTER_DOCTYPES)
	if unsupported:
		frappe.throw(_("Unsupported master DocTypes: {0}").format(", ".join(sorted(unsupported))))

	abbr = _company_abbr(company)
	messages = []
	if "Account" in doctypes:
		messages.extend(_export_accounts(company, abbr))
	if "Customer" in doctypes:
		messages.extend(_export_parties("Customer", "Sundry Debtors", company))
	if "Supplier" in doctypes:
		messages.extend(_export_parties("Supplier", "Sundry Creditors", company))
	if "Cost Center" in doctypes:
		messages.extend(_export_cost_centers(company, abbr))
	if "UOM" in doctypes:
		messages.extend(_export_uoms())
	if "Item Group" in doctypes:
		messages.extend(_export_item_groups())
	if "Warehouse" in doctypes:
		messages.extend(_export_warehouses(company, abbr))
	if "Item" in doctypes:
		messages.extend(_export_items())
	return _master_payload(messages)


def _parse_doctypes(doctypes):
	if not doctypes:
		return None
	if isinstance(doctypes, str):
		doctypes = json.loads(doctypes)
	if not isinstance(doctypes, (list, tuple)):
		frappe.throw(_("doctypes must be a JSON array"))
	return doctypes


def _amount(value):
	return f"{flt(value):.2f}"


def _quantity(value, uom):
	value = flt(value)
	number = f"{value:.6f}".rstrip("0").rstrip(".")
	return f"{number} {uom}".strip()


def _tally_date(value):
	return getdate(value).strftime("%Y%m%d")


def _tally_due_date(value):
	return formatdate(value, "d-MMM-yyyy")


def _sales_order_inventory_entry(item, order_name, company_abbr, income_account):
	uom = item.uom or item.stock_uom
	qty = _quantity(item.qty, uom)
	amount = _amount(item.base_net_amount)
	warehouse = _clean_name(item.warehouse, company_abbr)
	batch_allocation = {
		"orderno": order_name,
		"trackingnumber": "",
		"amount": amount,
		"actualqty": qty,
		"billedqty": qty,
		"orderduedate": _tally_due_date(item.delivery_date),
	}
	if warehouse:
		batch_allocation["godownname"] = warehouse
		batch_allocation["batchname"] = "Primary Batch"

	return {
		"stockitemname": item.item_code,
		"isdeemedpositive": False,
		"rate": f"{_amount(item.base_net_rate)}/{uom}",
		"amount": amount,
		"actualqty": qty,
		"billedqty": qty,
		"batchallocations": [batch_allocation],
		"accountingallocations": [
			{
				"ledgername": income_account,
				"isdeemedpositive": False,
				"amount": amount,
			}
		],
	}


def _sales_order_voucher(order, company_abbr, income_account):
	party = order.customer_name or order.customer
	party_amount = -flt(order.base_grand_total)
	ledger_entries = [
		{
			"ledgername": party,
			"isdeemedpositive": True,
			"ispartyledger": True,
			"islastdeemedpositive": True,
			"amount": _amount(party_amount),
		}
	]
	for tax in order.taxes:
		if not tax.account_head or not flt(tax.base_tax_amount_after_discount_amount):
			continue
		ledger_entries.append(
			{
				"ledgername": _clean_name(tax.account_head, company_abbr),
				"isdeemedpositive": False,
				"amount": _amount(tax.base_tax_amount_after_discount_amount),
			}
		)

	return {
		"metadata": _voucher_metadata(order.name),
		"date": _tally_date(order.transaction_date),
		"partyname": party,
		"partyledgername": party,
		"vouchertypename": "Sales Order",
		"vouchernumber": order.name,
		"reference": order.po_no or order.name,
		"narration": order.get("terms") or "",
		"persistedview": "Invoice Voucher View",
		"isoptional": True,
		"isorder": True,
		"ledgerentries": ledger_entries,
		"allinventoryentries": [
			_sales_order_inventory_entry(item, order.name, company_abbr, income_account)
			for item in order.items
		],
	}


def _validate_sales_order_filters(company, from_date, to_date):
	if not frappe.db.exists("Company", company):
		frappe.throw(_("Company {0} does not exist").format(frappe.bold(company)))
	if not from_date or not to_date:
		frappe.throw(_("From Date and To Date are required"))
	if getdate(from_date) > getdate(to_date):
		frappe.throw(_("From Date cannot be after To Date"))


def _sales_order_filters(company, from_date, to_date, customer=None, sales_order=None):
	filters = {
		"company": company,
		"docstatus": 1,
		"transaction_date": ["between", [from_date, to_date]],
	}
	if customer:
		filters["customer"] = customer
	if sales_order:
		filters["name"] = sales_order
	return filters


def _get_sales_orders(company, from_date, to_date, customer=None, sales_order=None):
	_validate_sales_order_filters(company, from_date, to_date)
	order_names = frappe.get_all(
		"Sales Order",
		filters=_sales_order_filters(company, from_date, to_date, customer, sales_order),
		pluck="name",
		order_by="transaction_date, name",
	)
	return [frappe.get_doc("Sales Order", name) for name in order_names]


def build_sales_order_master_payload(company, from_date, to_date, customer=None, sales_order=None):
	"""Return the masters referenced by the selected Sales Order vouchers."""
	orders = _get_sales_orders(company, from_date, to_date, customer, sales_order)
	if not orders:
		frappe.throw(_("No submitted Sales Orders match the selected filters."))

	item_codes = {item.item_code for order in orders for item in order.items if item.item_code}
	item_rows = frappe.get_all(
		"Item",
		filters={"name": ["in", sorted(item_codes)]},
		fields=["name", "item_group", "stock_uom"],
	)
	item_groups = {row.item_group for row in item_rows if row.item_group}
	uoms = {row.stock_uom for row in item_rows if row.stock_uom}
	uoms.update(item.uom for order in orders for item in order.items if item.uom)
	warehouses = {item.warehouse for order in orders for item in order.items if item.warehouse}
	customers = {order.customer for order in orders if order.customer}

	abbr = _company_abbr(company)
	messages = []
	messages.extend(_export_accounts(company, abbr, include_disabled=True))
	messages.extend(_export_parties("Customer", "Sundry Debtors", company, customers))
	messages.extend(_export_uoms(uoms))
	messages.extend(_export_item_groups(item_groups))
	messages.extend(_export_warehouses(company, abbr, warehouses))
	# Scoped exports intentionally include disabled/non-stock items because an old
	# submitted order can still reference them and Tally requires the exact master.
	messages.extend(_export_items(item_codes))
	return _master_payload(messages)


def build_sales_order_payload(company, from_date, to_date, customer=None, sales_order=None):
	"""Return submitted ERPNext Sales Orders as TallyPrime Sales Order vouchers."""
	orders = _get_sales_orders(company, from_date, to_date, customer, sales_order)
	abbr, default_income_account = frappe.db.get_value(
		"Company", company, ["abbr", "default_income_account"]
	)
	income_account = _clean_name(default_income_account, abbr) or "Sales"
	messages = [_sales_order_voucher(order, abbr, income_account) for order in orders]
	return {"tallymessage": messages}


@frappe.whitelist()
def get_supported_doctypes():
	return {"masters": SUPPORTED_MASTER_DOCTYPES}


@frappe.whitelist()
def get_export_summary(company):
	frappe.only_for(("Accounts Manager", "System Manager"))
	if not frappe.db.exists("Company", company):
		frappe.throw(_("Company {0} does not exist").format(frappe.bold(company)))
	return {
		"Account": frappe.db.count("Account", {"company": company, "disabled": 0}),
		"Customer": frappe.db.count("Customer", {"disabled": 0}),
		"Supplier": frappe.db.count("Supplier", {"disabled": 0}),
		"Cost Center": frappe.db.count("Cost Center", {"company": company, "disabled": 0}),
		"UOM": len(_export_uoms()),
		"Item Group": frappe.db.count("Item Group"),
		"Warehouse": frappe.db.count("Warehouse", {"company": company, "disabled": 0}),
		"Item": frappe.db.count("Item", {"disabled": 0, "is_stock_item": 1}),
	}


@frappe.whitelist()
def get_sales_order_count(company, from_date, to_date, customer=None, sales_order=None):
	frappe.only_for(("Accounts Manager", "System Manager"))
	_validate_sales_order_filters(company, from_date, to_date)
	return frappe.db.count(
		"Sales Order", _sales_order_filters(company, from_date, to_date, customer, sales_order)
	)


@frappe.whitelist()
def download_sales_order_masters_json(company, from_date, to_date, customer=None, sales_order=None):
	"""Download the masters required by the selected Sales Orders as UTF-16 JSON."""
	frappe.only_for(("Accounts Manager", "System Manager"))
	payload = build_sales_order_master_payload(company, from_date, to_date, customer, sales_order)
	content = json.dumps(payload, ensure_ascii=False, indent=4).encode("utf-16")
	filename = f"tally-required-masters-{getdate(from_date)}-to-{getdate(to_date)}.json"
	frappe.local.response.filename = filename
	frappe.local.response.filecontent = content
	frappe.local.response.type = "download"
	frappe.local.response.display_content_as = "attachment"


@frappe.whitelist()
def download_sales_order_json(company, from_date, to_date, customer=None, sales_order=None):
	"""Download submitted Sales Orders for TallyPrime 7.0+ as UTF-16 JSON."""
	frappe.only_for(("Accounts Manager", "System Manager"))
	payload = build_sales_order_payload(company, from_date, to_date, customer, sales_order)
	content = json.dumps(payload, ensure_ascii=False, indent=4).encode("utf-16")
	filename = f"tally-sales-orders-{getdate(from_date)}-to-{getdate(to_date)}.json"
	frappe.local.response.filename = filename
	frappe.local.response.filecontent = content
	frappe.local.response.type = "download"
	frappe.local.response.display_content_as = "attachment"


@frappe.whitelist()
def download_master_json(company, doctypes=None):
	"""Download master data for TallyPrime 7.0+ as UTF-16 native JSON."""
	frappe.only_for(("Accounts Manager", "System Manager"))
	payload = build_master_payload(company, _parse_doctypes(doctypes))
	content = json.dumps(payload, ensure_ascii=False, indent=4).encode("utf-16")
	filename = f"tally-masters-{frappe.scrub(company)}.json"
	frappe.local.response.filename = filename
	frappe.local.response.filecontent = content
	frappe.local.response.type = "download"
	frappe.local.response.display_content_as = "attachment"
