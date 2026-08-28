"""TallyPrime 7 native JSONEx payloads and import-result parsing."""

import uuid
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


def _amount(value):
	return str(Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _number(value):
	return format(Decimal(str(value or 0)).normalize(), "f")


def _quantity(value, unit):
	return f" {_number(value)} {unit}"


def _metadata(object_type, name, action="create", **values):
	return {"type": object_type, "action": action.lower(), "name": name, **values}


def _master_payload(company, messages):
	return {
		"static_variables": [
			{"name": "svMstImportFormat", "value": "jsonex"},
			{"name": "svCurrentCompany", "value": company},
		],
		"tallymessage": messages,
	}


def _unit(name):
	formal_names = {
		"Bag": "Bags",
		"Box": "Boxes",
		"Nos": "Numbers",
		"Pcs": "Pieces",
		"Kg": "Kilograms",
		"Ltr": "Litres",
		"Mtr": "Metres",
	}
	return {
		"metadata": _metadata("Unit", name),
		"name": name,
		"issimpleunit": True,
		"originalname": formal_names.get(name, name),
		"decimalplaces": "3",
	}


def _stock_group(group):
	return {
		"metadata": _metadata("Stock Group", group["name"]),
		"name": group["name"],
		"parent": group.get("parent") or "\x04 Primary",
		"shouldquantitiesbeadded": True,
	}


def _godown(name):
	return {
		"metadata": _metadata("Godown", name),
		"name": name,
		"parent": "\x04 Primary",
	}


def _ledger(name, parent, billwise=False, gstin="", country=""):
	ledger = {
		"metadata": _metadata("Ledger", name),
		"name": name,
		"parent": parent,
		"isbillwiseon": bool(billwise),
		"affectsstock": False,
	}
	if country:
		ledger["countryofresidence"] = country
	if gstin:
		ledger["partygstin"] = gstin
	return ledger


def _stock_item(item):
	stock_item = {
		"metadata": _metadata("Stock Item", item["item_code"]),
		"name": item["item_code"],
		"parent": item.get("item_group") or "\x04 Primary",
		"base units": item["stock_uom"],
		"gsttypeofsupply": "Goods",
	}
	if item.get("hsn_code"):
		stock_item["hsncode"] = item["hsn_code"]
	return stock_item


def build_master_imports(document, company):
	"""Return dependency-ordered native JSONEx master requests."""
	units = [_unit(name) for name in document["masters"]["units"]]
	general = [_stock_group(group) for group in document["masters"]["item_groups"]]
	general.extend(_godown(name) for name in document["masters"]["warehouses"])
	customer = document["customer"]
	general.append(
		_ledger(
			customer["name"],
			"Sundry Debtors",
			billwise=True,
			gstin=customer.get("gstin") or "",
			country=customer.get("country") or "",
		)
	)
	general.append(_ledger(document["sales_ledger"], "Sales Accounts"))
	general.extend(_ledger(tax["ledger"], "Duties & Taxes") for tax in document["taxes"])
	if document.get("rounding_adjustment"):
		general.append(_ledger(document["round_off_ledger"], "Indirect Expenses"))
	items = [_stock_item(item) for item in document["items"]]
	return [
		_master_payload(company, units),
		_master_payload(company, general),
		_master_payload(company, items),
	]


def _remote_id(document, target_id):
	source_doctype = document.get("source_doctype", "Sales Order")
	return str(
		uuid.uuid5(
			uuid.NAMESPACE_URL,
			f"srv-erp:{target_id}:{source_doctype}:Sales Voucher:{document['name']}",
		)
	)


def build_voucher_import(document, company, target_id):
	remote_id = _remote_id(document, target_id)
	party_amount = _amount(-Decimal(str(document["grand_total"])))
	voucher = {
		"metadata": _metadata(
			"Voucher",
			document["name"],
			document["operation"],
			vchtype="Sales",
			objview="Invoice Voucher View",
			remoteid=remote_id,
		),
		"guid": remote_id,
		"date": str(document["transaction_date"]).replace("-", "")[:8],
		"effectivedate": str(document["transaction_date"]).replace("-", "")[:8],
		"vouchertypename": "Sales",
		"vouchernumber": document["name"],
		"reference": document.get("reference") or document["name"],
		"partyname": document["customer"]["name"],
		"partyledgername": document["customer"]["name"],
		"basicbuyername": document["customer"]["name"],
		"narration": document.get("narration")
		or f"ERPNext {document.get('source_doctype', 'Sales Order')} {document['name']}",
		"persistedview": "Invoice Voucher View",
		"vchentrymode": "Item Invoice",
		"isoptional": False,
		"isinvoice": True,
		"isorder": False,
		"ledgerentries": [
			{
				"ledgername": document["customer"]["name"],
				"isdeemedpositive": True,
				"ispartyledger": True,
				"islastdeemedpositive": True,
				"amount": party_amount,
				"billallocations": [
					{
						"name": document["name"],
						"billtype": "New Ref",
						"amount": party_amount,
					}
				],
			}
		],
		"allinventoryentries": [],
	}

	for tax in document["taxes"]:
		voucher["ledgerentries"].append(
			{
				"ledgername": tax["ledger"],
				"isdeemedpositive": False,
				"amount": _amount(tax["amount"]),
			}
		)
	if document.get("rounding_adjustment"):
		rounding = Decimal(str(document["rounding_adjustment"]))
		voucher["ledgerentries"].append(
			{
				"ledgername": document["round_off_ledger"],
				"isdeemedpositive": rounding < 0,
				"amount": _amount(rounding),
			}
		)

	for item in document["items"]:
		qty = _quantity(item["stock_qty"], item["stock_uom"])
		batch = {
			"batchname": "Primary Batch",
			"amount": _amount(item["amount"]),
			"actualqty": qty,
			"billedqty": qty,
		}
		if item.get("warehouse"):
			batch["godownname"] = item["warehouse"]
		voucher["allinventoryentries"].append(
			{
				"stockitemname": item["item_code"],
				"isdeemedpositive": False,
				"rate": f"{_amount(item['rate'])}/{item['stock_uom']}",
				"amount": _amount(item["amount"]),
				"actualqty": qty,
				"billedqty": qty,
				"batchallocations": [batch],
				"accountingallocations": [
					{
						"ledgername": document["sales_ledger"],
						"isdeemedpositive": False,
						"amount": _amount(item["amount"]),
					}
				],
			}
		)
	return {
		"static_variables": [
			{"name": "svVchImportFormat", "value": "jsonex"},
			{"name": "svCurrentCompany", "value": company},
		],
		"tallymessage": [voucher],
	}


@dataclass(frozen=True)
class ImportResult:
	success: bool
	created: int = 0
	altered: int = 0
	ignored: int = 0
	errors: int = 0
	last_voucher_id: str = ""
	message: str = ""


def parse_import_response(payload, require_change=False, allow_ignored=False):
	result = payload.get("data", {}).get("import_result", {})
	created = int(result.get("created") or 0)
	altered = int(result.get("altered") or 0)
	ignored = int(result.get("ignored") or 0)
	errors = int(result.get("errors") or 0)
	exceptions = int(result.get("exceptions") or 0)
	cancelled = int(result.get("cancelled") or 0)
	changed = created + altered + int(result.get("combined") or 0) + cancelled
	accepted = changed > 0 or (allow_ignored and ignored > 0)
	messages = result.get("line_errors") or result.get("lineerror") or payload.get("error") or ""
	if isinstance(messages, list):
		messages = "; ".join(str(message) for message in messages)
	if not messages and (errors or exceptions):
		messages = f"Tally reported errors={errors}, exceptions={exceptions}"
	success = (
		str(payload.get("status", "1")) != "0"
		and errors == 0
		and exceptions == 0
		and not messages
		and (not require_change or accepted)
	)
	if require_change and not accepted and not messages:
		messages = f"Tally did not create or alter the voucher (ignored={ignored})"
	return ImportResult(
		success=success,
		created=created,
		altered=altered,
		ignored=ignored,
		errors=errors,
		last_voucher_id=str(result.get("lastvchid") or ""),
		message=str(messages),
	)
