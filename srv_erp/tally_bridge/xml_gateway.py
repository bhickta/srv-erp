import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP


def _element(parent, tag, value=None, **attributes):
	element = ET.SubElement(parent, tag, {key.upper(): str(value) for key, value in attributes.items()})
	if value is not None:
		element.text = str(value)
	return element


def _yes_no(value):
	return "Yes" if value else "No"


def _amount(value):
	return str(Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _number(value):
	number = Decimal(str(value or 0)).normalize()
	return format(number, "f")


def _date(value):
	if isinstance(value, (date, datetime)):
		return value.strftime("%Y%m%d")
	return datetime.strptime(str(value)[:10], "%Y-%m-%d").strftime("%Y%m%d")


def _due_date(value):
	if isinstance(value, (date, datetime)):
		return value.strftime("%d-%b-%Y")
	return datetime.strptime(str(value)[:10], "%Y-%m-%d").strftime("%d-%b-%Y")


def _quantity(value, unit):
	return f"{_number(value)} {unit}".strip()


def _envelope(request, request_type, report_id, company=None):
	root = ET.Element("ENVELOPE")
	header = _element(root, "HEADER")
	_element(header, "VERSION", "1")
	_element(header, "TALLYREQUEST", request)
	_element(header, "TYPE", request_type)
	_element(header, "ID", report_id)
	body = _element(root, "BODY")
	desc = _element(body, "DESC")
	if company:
		variables = _element(desc, "STATICVARIABLES")
		_element(variables, "SVCURRENTCOMPANY", company)
	return root, body, desc


def current_company_request():
	root, _, _ = _envelope("EXPORT", "FUNCTION", "$$CurrentCompany")
	return ET.tostring(root, encoding="unicode")


def function_request(function_name):
	if not function_name.startswith("$$"):
		raise ValueError("Only built-in Tally functions may be queried")
	root, _, _ = _envelope("EXPORT", "FUNCTION", function_name)
	return ET.tostring(root, encoding="unicode")


def _import_envelope(report_id, company):
	root, body, desc = _envelope("Import", "Data", report_id, company)
	variables = desc.find("STATICVARIABLES")
	_element(variables, "IMPORTDUPS", "@@DUPIGNORE")
	data = _element(body, "DATA")
	message = _element(data, "TALLYMESSAGE")
	return root, message


def _group(message, name, parent=""):
	group = _element(message, "STOCKGROUP", name=name, action="Create")
	_element(group, "NAME", name)
	_element(group, "PARENT", parent)
	_element(group, "SHOULDQUANTITIESBEADDED", "Yes")


def _unit(message, name):
	# TallyPrime treats NAME as a method (not an identifying XML attribute) for
	# Unit masters. Supplying NAME as an attribute makes 7.1 silently ignore it.
	unit = _element(message, "UNIT", action="Create")
	_element(unit, "NAME", name)
	_element(unit, "ISSIMPLEUNIT", "Yes")
	_element(unit, "ORIGINALNAME", name)
	_element(unit, "DECIMALPLACES", "3")


def _godown(message, name):
	godown = _element(message, "GODOWN", name=name, action="Create")
	_element(godown, "NAME", name)
	_element(godown, "PARENT", "")


def _ledger(message, name, parent, billwise=False, gstin="", country=""):
	ledger = _element(message, "LEDGER", name=name, action="Create")
	_element(ledger, "NAME", name)
	_element(ledger, "PARENT", parent)
	_element(ledger, "ISBILLWISEON", _yes_no(billwise))
	_element(ledger, "AFFECTSSTOCK", "No")
	if country:
		_element(ledger, "COUNTRYOFRESIDENCE", country)
	if gstin:
		_element(ledger, "PARTYGSTIN", gstin)
		_element(ledger, "GSTREGISTRATIONTYPE", "Regular")


def _stock_item(message, item):
	stock_item = _element(message, "STOCKITEM", name=item["item_code"], action="Create")
	_element(stock_item, "NAME", item["item_code"])
	_element(stock_item, "PARENT", item.get("item_group") or "")
	_element(stock_item, "BASEUNITS", item["stock_uom"])
	_element(stock_item, "DESCRIPTION", item.get("description") or item.get("item_name") or "")
	_element(stock_item, "ISBATCHWISEON", "No")
	_element(stock_item, "ISGODOWNON", "Yes")
	if item.get("hsn_code"):
		_element(stock_item, "GSTAPPLICABLE", "Applicable")
		_element(stock_item, "HSNCODE", item["hsn_code"])


def build_master_import(order, company):
	"""Build one combined master request (primarily useful for inspection)."""
	root, message = _import_envelope("All Masters", company)
	for group in order["masters"]["item_groups"]:
		_group(message, group["name"], group.get("parent") or "")
	for unit in order["masters"]["units"]:
		_unit(message, unit)
	for warehouse in order["masters"]["warehouses"]:
		_godown(message, warehouse)

	customer = order["customer"]
	_ledger(
		message,
		customer["name"],
		"Sundry Debtors",
		billwise=True,
		gstin=customer.get("gstin") or "",
		country=customer.get("country") or "",
	)
	_ledger(message, order["sales_ledger"], "Sales Accounts")
	for tax in order["taxes"]:
		_ledger(message, tax["ledger"], "Duties & Taxes")
	if order.get("rounding_adjustment"):
		_ledger(message, order["round_off_ledger"], "Indirect Expenses")
	for item in order["items"]:
		_stock_item(message, item)
	return ET.tostring(root, encoding="unicode")


def build_master_imports(order, company):
	"""Build dependency-ordered requests so Tally cannot skip dependent items.

	TallyPrime may report a missing Unit as an ignored object when Unit and Stock
	Item masters share one import request. Sending the three dependency layers
	separately gives every response an unambiguous result.
	"""
	requests = []

	root, message = _import_envelope("All Masters", company)
	for unit in order["masters"]["units"]:
		_unit(message, unit)
	requests.append(ET.tostring(root, encoding="unicode"))

	root, message = _import_envelope("All Masters", company)
	for group in order["masters"]["item_groups"]:
		_group(message, group["name"], group.get("parent") or "")
	for warehouse in order["masters"]["warehouses"]:
		_godown(message, warehouse)
	customer = order["customer"]
	_ledger(
		message,
		customer["name"],
		"Sundry Debtors",
		billwise=True,
		gstin=customer.get("gstin") or "",
		country=customer.get("country") or "",
	)
	_ledger(message, order["sales_ledger"], "Sales Accounts")
	for tax in order["taxes"]:
		_ledger(message, tax["ledger"], "Duties & Taxes")
	if order.get("rounding_adjustment"):
		_ledger(message, order["round_off_ledger"], "Indirect Expenses")
	requests.append(ET.tostring(root, encoding="unicode"))

	root, message = _import_envelope("All Masters", company)
	for item in order["items"]:
		_stock_item(message, item)
	requests.append(ET.tostring(root, encoding="unicode"))
	return requests


def _voucher_attributes(order, target_id):
	source_doctype = order.get("source_doctype", "Sales Order")
	remote_id = str(
		uuid.uuid5(
			uuid.NAMESPACE_URL,
			f"srv-erp:{target_id}:{source_doctype}:Sales Voucher:{order['name']}",
		)
	)
	attributes = {
		"REMOTEID": remote_id,
		"VCHTYPE": "Sales",
		"ACTION": order["operation"],
		"OBJVIEW": "Accounting Voucher View",
	}
	if order["operation"] == "Alter":
		if order.get("tally_voucher_id"):
			attributes.update(
				{"TAGNAME": "MASTER ID", "TAGVALUE": order["tally_voucher_id"]}
			)
		else:
			attributes.update({"TAGNAME": "Voucher Number", "TAGVALUE": order["name"]})
	return attributes, remote_id


def build_voucher_import(order, company, target_id):
	root, message = _import_envelope("Vouchers", company)
	attributes, remote_id = _voucher_attributes(order, target_id)
	voucher = _element(message, "VOUCHER", **attributes)
	_element(voucher, "GUID", remote_id)
	_element(voucher, "DATE", _date(order["transaction_date"]))
	_element(voucher, "VOUCHERTYPENAME", "Sales")
	_element(voucher, "VOUCHERNUMBER", order["name"])
	_element(voucher, "REFERENCE", order.get("reference") or order["name"])
	_element(voucher, "PARTYNAME", order["customer"]["name"])
	_element(voucher, "PARTYLEDGERNAME", order["customer"]["name"])
	source_doctype = order.get("source_doctype", "Sales Order")
	_element(
		voucher,
		"NARRATION",
		order.get("narration") or f"ERPNext {source_doctype} {order['name']}",
	)
	_element(voucher, "PERSISTEDVIEW", "Accounting Voucher View")
	_element(voucher, "ISINVOICE", "No")
	_element(voucher, "ISORDER", "No")
	_element(voucher, "ISOPTIONAL", "No")

	grand_total = Decimal(str(order["grand_total"] or 0))
	party_entry = _element(voucher, "LEDGERENTRIES.LIST")
	_element(party_entry, "LEDGERNAME", order["customer"]["name"])
	_element(party_entry, "ISDEEMEDPOSITIVE", "Yes")
	_element(party_entry, "ISPARTYLEDGER", "Yes")
	_element(party_entry, "ISLASTDEEMEDPOSITIVE", "Yes")
	if grand_total:
		_element(party_entry, "AMOUNT", _amount(-grand_total))
		bill = _element(party_entry, "BILLALLOCATIONS.LIST")
		_element(bill, "NAME", order["name"])
		_element(bill, "BILLTYPE", "New Ref")
		_element(bill, "AMOUNT", _amount(-grand_total))


	sales_entry = _element(voucher, "LEDGERENTRIES.LIST")
	_element(sales_entry, "LEDGERNAME", order["sales_ledger"])
	_element(sales_entry, "ISDEEMEDPOSITIVE", "No")
	net_total = Decimal(
		str(order.get("net_total") or sum(Decimal(str(item["amount"] or 0)) for item in order["items"]))
	)
	if net_total:
		_element(sales_entry, "AMOUNT", _amount(net_total))

	for item in order["items"]:
		item_amount = Decimal(str(item["amount"] or 0))
		inventory = _element(sales_entry, "INVENTORYALLOCATIONS.LIST")
		_element(inventory, "STOCKITEMNAME", item["item_code"])
		_element(inventory, "ISDEEMEDPOSITIVE", "No")
		if item_amount:
			_element(inventory, "RATE", f"{_amount(item['rate'])}/{item['stock_uom']}")
			_element(inventory, "AMOUNT", _amount(item_amount))
		qty = _quantity(item["stock_qty"], item["stock_uom"])
		_element(inventory, "ACTUALQTY", qty)
		_element(inventory, "BILLEDQTY", qty)

		if item.get("warehouse"):
			batch = _element(inventory, "BATCHALLOCATIONS.LIST")
			_element(batch, "GODOWNNAME", item["warehouse"])
			_element(batch, "BATCHNAME", "Primary Batch")
			if item_amount:
				_element(batch, "AMOUNT", _amount(item_amount))
			_element(batch, "ACTUALQTY", qty)
			_element(batch, "BILLEDQTY", qty)

	for tax in order["taxes"]:
		tax_entry = _element(voucher, "LEDGERENTRIES.LIST")
		_element(tax_entry, "LEDGERNAME", tax["ledger"])
		_element(tax_entry, "ISDEEMEDPOSITIVE", "No")
		_element(tax_entry, "AMOUNT", _amount(tax["amount"]))

	if order.get("rounding_adjustment"):
		rounding_entry = _element(voucher, "LEDGERENTRIES.LIST")
		_element(rounding_entry, "LEDGERNAME", order["round_off_ledger"])
		is_positive = Decimal(str(order["rounding_adjustment"])) < 0
		_element(rounding_entry, "ISDEEMEDPOSITIVE", _yes_no(is_positive))
		_element(rounding_entry, "AMOUNT", _amount(order["rounding_adjustment"]))
	return ET.tostring(root, encoding="unicode")


@dataclass(frozen=True)
class ImportResult:
	success: bool
	created: int = 0
	altered: int = 0
	ignored: int = 0
	errors: int = 0
	last_voucher_id: str = ""
	message: str = ""


def _text(root, name, default=""):
	element = root.find(f".//{name}")
	return (element.text or default).strip() if element is not None else default


def _integer(root, name):
	try:
		return int(_text(root, name, "0"))
	except ValueError:
		return 0


def parse_import_response(xml, require_change=False, allow_ignored=False):
	try:
		root = ET.fromstring(xml)
	except ET.ParseError as exc:
		raise ValueError(f"Tally returned invalid XML: {xml[:500]}") from exc
	created = _integer(root, "CREATED")
	altered = _integer(root, "ALTERED")
	ignored = _integer(root, "IGNORED")
	errors = _integer(root, "ERRORS")
	exceptions = _integer(root, "EXCEPTIONS")
	status = _text(root, "STATUS", "1")
	line_errors = [
		(element.text or "").strip()
		for element in root.findall(".//LINEERROR")
		if (element.text or "").strip()
	]
	message = "; ".join(line_errors) or _text(root, "DATA")
	if not message and (errors or exceptions):
		message = f"Tally reported errors={errors}, exceptions={exceptions}"
	changed = created + altered + _integer(root, "COMBINED") + _integer(root, "CANCELLED")
	accepted = changed > 0 or (allow_ignored and ignored > 0)
	success = (
		status != "0"
		and errors == 0
		and exceptions == 0
		and not line_errors
		and (not require_change or accepted)
	)
	if require_change and not accepted and not message:
		message = f"Tally did not create or alter the voucher (ignored={ignored})"
	return ImportResult(
		success=success,
		created=created,
		altered=altered,
		ignored=ignored,
		errors=errors,
		last_voucher_id=_text(root, "LASTVCHID"),
		message=message,
	)


def parse_current_company(xml):
	try:
		root = ET.fromstring(xml)
	except ET.ParseError as exc:
		raise ValueError("Tally returned invalid XML") from exc
	return _text(root, "RESULT")


def parse_logical_result(xml):
	return parse_current_company(xml).strip().lower() in {"yes", "true", "1"}
