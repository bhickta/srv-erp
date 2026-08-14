from __future__ import annotations

import unicodedata
from decimal import Decimal, InvalidOperation

import frappe
from frappe import _
from frappe.utils import cstr

from srv_erp.masters.dynamic_item.lookups import get_case_insensitive_name

MAX_ATTRIBUTES = 20
MAX_PACKAGING_UOMS = 10


def parse_payload(payload) -> frappe._dict:
	if isinstance(payload, str):
		payload = frappe.parse_json(payload)
	if not isinstance(payload, dict):
		frappe.throw(_("Request payload must be a JSON object."))
	return frappe._dict(payload)


def normalize_text(value, label: str) -> str:
	value = unicodedata.normalize("NFC", cstr(value)).strip()
	if not value:
		frappe.throw(_("{0} cannot be empty.").format(label))
	return value


def normalize_attributes(attributes) -> dict[str, str]:
	if not isinstance(attributes, dict):
		frappe.throw(_("Attributes must be an object mapping attribute names to values."))
	if not attributes:
		frappe.throw(_("Specify at least one variant attribute."))
	if len(attributes) > MAX_ATTRIBUTES:
		frappe.throw(_("A request can contain at most {0} attributes.").format(MAX_ATTRIBUTES))

	normalized = {}
	seen = set()
	for raw_attribute, raw_value in attributes.items():
		attribute = normalize_text(raw_attribute, _("Attribute"))
		value = normalize_text(raw_value, _("Attribute Value"))
		key = attribute.casefold()
		if key in seen:
			frappe.throw(_("Attribute {0} is specified more than once.").format(frappe.bold(attribute)))
		seen.add(key)
		normalized[attribute] = value
	return normalized


def normalize_uoms(uoms) -> list[dict]:
	if uoms is None:
		return []
	if not isinstance(uoms, list):
		frappe.throw(_("UOMs must be an array."))
	if len(uoms) > MAX_PACKAGING_UOMS:
		frappe.throw(_("A request can contain at most {0} packaging UOMs.").format(MAX_PACKAGING_UOMS))

	normalized = []
	seen = set()
	for row in uoms:
		if not isinstance(row, dict):
			frappe.throw(_("Each packaging UOM must be an object."))
		uom = normalize_text(row.get("uom"), _("UOM"))
		canonical_uom = get_case_insensitive_name("UOM", uom)
		if not canonical_uom:
			frappe.throw(_("UOM {0} does not exist.").format(frappe.bold(uom)))
		key = canonical_uom.casefold()
		if key in seen:
			frappe.throw(_("UOM {0} is specified more than once.").format(frappe.bold(canonical_uom)))
		seen.add(key)
		try:
			factor = Decimal(cstr(row.get("conversion_factor")))
		except (InvalidOperation, TypeError):
			frappe.throw(_("Conversion Factor for {0} must be a number.").format(frappe.bold(canonical_uom)))
		if not factor.is_finite() or factor <= 0:
			frappe.throw(
				_("Conversion Factor for {0} must be greater than zero.").format(frappe.bold(canonical_uom))
			)
		normalized.append({"uom": canonical_uom, "conversion_factor": cstr(factor.normalize())})
	return sorted(normalized, key=lambda row: row["uom"].casefold())
