import hashlib
import json

from frappe.utils import cstr


def make_identity_signature(template_item: str, attributes: dict[str, str]) -> str:
	payload = {
		"template_item": template_item,
		"attributes": sorted((attribute, cstr(value)) for attribute, value in attributes.items()),
	}
	return hashlib.sha256(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def make_packaging_signature(item_code: str, uoms: list[dict]) -> str:
	payload = {"item_code": item_code, "uoms": uoms}
	return hashlib.sha256(
		json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
	).hexdigest()
