from string import Formatter

import frappe
from frappe.contacts.doctype.address.address import render_address
from frappe.model.rename_doc import get_link_fields
from erpnext.accounts.party import get_party_shipping_address


def sync_customer_linked_docs(doc, method):
	if method != "on_update":
		return

	_sync_customer_linked_docs(doc)


def sync_customer_linked_docs_after_rename(doc, method, *args):
	if method != "after_rename":
		return

	_sync_customer_linked_docs(doc, args[1])


def sync_address_linked_docs(doc, method=None):
	if method not in ("on_update", "after_rename"):
		return

	address_name = doc.name
	address_display = render_address(doc.as_dict(), check_permissions=False)
	customer_names = {
		link.link_name
		for link in doc.get("links", [])
		if link.link_doctype == "Customer"
	}

	old_doc = doc.get_doc_before_save()
	if old_doc:
		customer_names.update(
			link.link_name
			for link in old_doc.get("links", [])
			if link.link_doctype == "Customer"
		)

	for customer_name in customer_names:
		customer = frappe.get_doc("Customer", customer_name)
		address_values = _get_customer_address_values(customer_name)
		if address_name in (
			address_values["billing_address"],
			address_values["shipping_address"],
		):
			_sync_customer_linked_docs(customer)
		else:
			_sync_address_display_for_customer(customer_name, address_name, address_display)


def _sync_customer_linked_docs(customer, customer_id=None):
	customer_id = customer_id or customer.name
	customer_values = customer.as_dict()
	customer_values["name"] = customer_id
	address_values = _get_customer_address_values(customer_id)

	link_fields_by_doctype = {}
	for link_field in get_link_fields("Customer"):
		if not link_field["issingle"]:
			link_fields_by_doctype.setdefault(link_field["parent"], []).append(
				link_field["fieldname"]
			)

	for doctype, link_fieldnames in link_fields_by_doctype.items():
		meta = frappe.get_meta(doctype)
		if meta.is_virtual:
			continue

		for link_fieldname in link_fieldnames:
			fetch_fields = [
				field
				for field in meta.get_fields_to_fetch(link_fieldname)
				if not field.get("is_virtual")
			]
			fetch_values = {
				field.fieldname: customer_values.get(field.fetch_from.split(".", 1)[1])
				for field in fetch_fields
			}

			customer_name_field = meta.get_field("customer_name")
			if customer_name_field and customer_name_field.fieldtype in ("Data", "Read Only"):
				fetch_values["customer_name"] = customer_values.get("customer_name")

			fetch_values.update(_get_address_field_values(meta, address_values))
			title_template = _get_customer_title_template(meta, customer_values)
			title_keys = _template_keys(title_template) if title_template else set()
			target_fields = {"name", link_fieldname, *fetch_values}
			target_fields.update(key for key in title_keys if meta.has_field(key))

			rows = frappe.get_all(
				doctype,
				filters={link_fieldname: customer_id},
				fields=sorted(target_fields),
			)
			for row in rows:
				values = dict(fetch_values)
				if title_template:
					title_fieldname = meta.get_title_field()
					format_values = dict(row)
					format_values.update(customer_values)
					format_values["name"] = row.name
					values[title_fieldname] = title_template.format(**format_values)

				if values:
					# Keep linked snapshots current without changing transaction timestamps.
					frappe.db.set_value(
						doctype,
						row.name,
						values,
						update_modified=False,
					)


def _get_customer_address_values(customer_id):
	billing_address = frappe.db.get_value("Customer", customer_id, "customer_primary_address")
	shipping_address = get_party_shipping_address("Customer", customer_id)

	return {
		"billing_address": billing_address,
		"billing_address_display": _get_address_display(billing_address),
		"shipping_address": shipping_address,
		"shipping_address_display": _get_address_display(shipping_address),
	}


def _get_address_field_values(meta, address_values):
	values = {}
	for field in meta.get_link_fields():
		if field.options != "Address":
			continue

		if field.fieldname in ("customer_address", "billing_address", "billing_address_name"):
			address_key = "billing_address"
		elif "shipping" in field.fieldname:
			address_key = "shipping_address"
		else:
			continue

		address = address_values[address_key]
		if not address:
			continue

		values[field.fieldname] = address
		display_fieldname = _address_display_field(field.fieldname)
		if meta.has_field(display_fieldname):
			values[display_fieldname] = address_values[f"{address_key}_display"]

	return values


def _get_customer_title_template(meta, customer_values):
	title_fieldname = meta.get_title_field()
	title_field = meta.get_field(title_fieldname)
	if not title_field:
		return None

	template = title_field.options or title_field.default
	if not template:
		return None

	return template if _template_keys(template) & customer_values.keys() else None


def _template_keys(template):
	return {key for _, key, _, _ in Formatter().parse(template) if key}


def _address_display_field(fieldname):
	if fieldname == "customer_address":
		return "address_display"
	if fieldname in ("billing_address", "billing_address_name"):
		return "billing_address_display"
	if fieldname.endswith("_name"):
		return fieldname.removesuffix("_name")
	return f"{fieldname}_display"


def _sync_address_display_for_customer(customer_id, address_name, address_display):
	for link_field in get_link_fields("Customer"):
		if link_field["issingle"]:
			continue

		doctype = link_field["parent"]
		meta = frappe.get_meta(doctype)
		if meta.is_virtual:
			continue

		for field in meta.get_link_fields():
			if field.options != "Address":
				continue

			display_fieldname = _address_display_field(field.fieldname)
			if not meta.has_field(display_fieldname):
				continue

			frappe.db.set_value(
				doctype,
				{
					link_field["fieldname"]: customer_id,
					field.fieldname: address_name,
				},
				display_fieldname,
				address_display,
				update_modified=False,
			)


def _get_address_display(address_name):
	if not address_name:
		return None

	address = frappe.get_doc("Address", address_name)
	return render_address(address.as_dict(), check_permissions=False)
