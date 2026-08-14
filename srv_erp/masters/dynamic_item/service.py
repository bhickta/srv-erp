from __future__ import annotations

import hashlib
import json
import unicodedata
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation

import frappe
from erpnext.controllers.item_variant import (
	create_variant,
	get_variant,
	validate_is_incremental,
)
from frappe import _
from frappe.utils import cint, cstr, flt, now_datetime

from srv_erp.item.variant_auto_creation import (
	get_brand_abbreviation,
	is_brand_disabled,
	make_attribute_abbr,
)
from srv_erp.masters.dynamic_item.configuration import (
	ADD_PACKAGING,
	APPROVED,
	CANCELLED,
	CREATE_VARIANT,
	PENDING,
	REJECTED,
	get_approver_users,
	get_settings,
	is_grid_enabled,
	require_approver,
	require_requester,
	user_has_approver_role,
)

MAX_ATTRIBUTES = 20
MAX_PACKAGING_UOMS = 10


class DynamicItemConflict(frappe.ValidationError):
	pass


@contextmanager
def dynamic_item_service_context():
	previous = getattr(frappe.flags, "dynamic_item_service", False)
	frappe.flags.dynamic_item_service = True
	try:
		yield
	finally:
		frappe.flags.dynamic_item_service = previous


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


def get_case_insensitive_name(doctype: str, value: str) -> str | None:
	table = {
		"Item Attribute": "`tabItem Attribute`",
		"Item Attribute Value": "`tabItem Attribute Value`",
		"Brand": "`tabBrand`",
		"UOM": "`tabUOM`",
	}.get(doctype)
	if not table:
		frappe.throw(_("Unsupported master lookup: {0}").format(doctype))

	field = "attribute_value" if doctype == "Item Attribute Value" else "name"
	params = {"value": value}
	if doctype == "Item Attribute Value":
		frappe.throw(_("Item Attribute Value lookup requires an attribute."))
	rows = frappe.db.sql(
		f"select `{field}` from {table} where lower(`{field}`) = lower(%(value)s) order by creation limit 1",
		params,
	)
	return rows[0][0] if rows else None


def get_case_insensitive_attribute_value(attribute: str, value: str) -> str | None:
	rows = frappe.db.sql(
		"""
		select attribute_value
		from `tabItem Attribute Value`
		where parent = %(attribute)s
			and lower(attribute_value) = lower(%(value)s)
		order by idx
		limit 1
		""",
		{"attribute": attribute, "value": value},
	)
	return rows[0][0] if rows else None


def canonicalize_known_masters(attributes: dict[str, str]) -> dict[str, str]:
	canonical = {}
	for attribute, value in attributes.items():
		canonical_attribute = get_case_insensitive_name("Item Attribute", attribute) or attribute
		canonical_value = (
			get_case_insensitive_attribute_value(canonical_attribute, value)
			if frappe.db.exists("Item Attribute", canonical_attribute)
			else None
		)
		canonical[canonical_attribute] = canonical_value or value
	return canonical


def validate_source(source):
	if not source:
		return frappe._dict()
	if not isinstance(source, dict):
		frappe.throw(_("Source must be a JSON object."))
	source = frappe._dict(source)
	if source.doctype or source.fieldname:
		if not source.doctype or not source.fieldname:
			frappe.throw(_("Source DocType and fieldname must be supplied together."))
		if not is_grid_enabled(source.doctype, source.fieldname):
			frappe.throw(
				_("Dynamic Item Requests are not enabled for {0}.{1}.").format(
					frappe.bold(source.doctype), frappe.bold(source.fieldname)
				)
			)
	return source


def get_template_and_profile(template_item: str):
	template_item = normalize_text(template_item, _("Item Template"))
	template = frappe.get_doc("Item", template_item)
	if not template.has_permission("read"):
		frappe.throw(_("Not permitted to read Item template {0}.").format(frappe.bold(template_item)))
	if template.disabled:
		frappe.throw(_("Item template {0} is disabled.").format(frappe.bold(template_item)))
	if not cint(template.has_variants) or template.variant_based_on != "Item Attribute":
		frappe.throw(_("{0} is not an Item Attribute-based template.").format(frappe.bold(template_item)))
	if not frappe.db.exists("Dynamic Variant Profile", template_item):
		frappe.throw(
			_("Dynamic Variant Profile is not configured for {0}.").format(frappe.bold(template_item))
		)
	profile = frappe.get_doc("Dynamic Variant Profile", template_item)
	if not cint(profile.enabled):
		frappe.throw(_("Dynamic Variant Profile is disabled for {0}.").format(frappe.bold(template_item)))
	return template, profile


def get_profile_rules(profile) -> dict[str, frappe._dict]:
	return {row.item_attribute: row for row in profile.get("attributes") or [] if row.item_attribute}


def validate_requested_attributes(template, profile, attributes: dict[str, str]):
	rules = get_profile_rules(profile)
	missing = [
		attribute
		for attribute, rule in rules.items()
		if cint(rule.required_parameter) and not attributes.get(attribute)
	]
	if missing:
		frappe.throw(
			_("Missing required variant attributes: {0}.").format(
				", ".join(frappe.bold(attribute) for attribute in missing)
			)
		)

	settings = get_settings()
	template_attributes = {row.attribute for row in template.get("attributes") or []}
	for attribute, value in attributes.items():
		rule = rules.get(attribute)
		attribute_exists = frappe.db.exists("Item Attribute", attribute)
		if attribute.casefold() == "brand":
			brand = get_case_insensitive_name("Brand", value)
			if brand and is_brand_disabled(brand):
				frappe.throw(_("Brand {0} is disabled.").format(frappe.bold(brand)))
		if not rule and not cint(settings.allow_dynamic_attributes):
			frappe.throw(_("Attribute {0} is not allowed by this profile.").format(frappe.bold(attribute)))
		if attribute_exists and cint(frappe.db.get_value("Item Attribute", attribute, "numeric_values")):
			if not rule or attribute not in template_attributes:
				frappe.throw(
					_("Numeric attribute {0} must be configured on the template profile first.").format(
						frappe.bold(attribute)
					)
				)
			validate_numeric_value(template.name, attribute, value)
		elif attribute_exists and not get_case_insensitive_attribute_value(attribute, value):
			if rule and not cint(rule.allow_new_values):
				frappe.throw(
					_("New values are not allowed for attribute {0}.").format(frappe.bold(attribute))
				)


def validate_numeric_value(template_item: str, attribute: str, value: str):
	row = frappe.db.get_value(
		"Item Variant Attribute",
		{"parent": template_item, "attribute": attribute},
		["from_range", "to_range", "increment"],
		as_dict=True,
	)
	if not row:
		frappe.throw(_("Numeric attribute {0} is not configured on the template.").format(attribute))
	validate_is_incremental(row, attribute, value, template_item)


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


def get_item_state(item_code: str) -> frappe._dict:
	return frappe.db.get_value(
		"Item",
		item_code,
		["name", "disabled", "dynamic_item_approval_status", "dynamic_item_request"],
		as_dict=True,
	)


def get_variant_if_present(template_item: str, attributes: dict[str, str]) -> str | None:
	return get_variant(template_item, attributes)


def get_pending_request(active_signature: str):
	return frappe.db.get_value(
		"Dynamic Item Request",
		{"active_signature": active_signature, "status": PENDING},
		["name", "request_type", "status", "staged_item_code", "resolved_item"],
		as_dict=True,
	)


def request_result(request, created: bool = False) -> dict:
	return {
		"outcome": "packaging_approval_required"
		if request.request_type == ADD_PACKAGING
		else "pending_approval",
		"item_code": request.staged_item_code or request.resolved_item,
		"request": request.name,
		"approval_status": request.status,
		"created": bool(created),
	}


def existing_result(item_code: str) -> dict:
	return {
		"outcome": "existing",
		"item_code": item_code,
		"request": None,
		"approval_status": APPROVED,
		"created": False,
	}


def get_missing_packaging(item, uoms: list[dict]) -> list[dict]:
	existing = {row.uom: flt(row.conversion_factor) for row in item.get("uoms") or [] if row.uom}
	missing = []
	for row in uoms:
		uom = row["uom"]
		factor = flt(row["conversion_factor"])
		if uom in existing:
			if flt(existing[uom], 9) != flt(factor, 9):
				frappe.throw(
					_(
						"UOM {0} already has conversion factor {1}; requested factor {2} is a conflict."
					).format(frappe.bold(uom), existing[uom], factor),
					DynamicItemConflict,
				)
			continue
		if uom == item.stock_uom:
			if flt(factor, 9) != 1:
				frappe.throw(_("Stock UOM {0} must have conversion factor 1.").format(frappe.bold(uom)))
			continue
		missing.append({"uom": uom, "conversion_factor": factor})
	return missing


def validate_existing_variant(item_code: str):
	state = get_item_state(item_code)
	if not state:
		return
	if state.dynamic_item_approval_status == PENDING and state.dynamic_item_request:
		request = frappe.get_doc("Dynamic Item Request", state.dynamic_item_request)
		return request_result(request)
	if cint(state.disabled):
		frappe.throw(
			_("Matching Item {0} exists but is disabled; reactivate or resolve it in Masters.").format(
				frappe.bold(item_code)
			),
			DynamicItemConflict,
		)
	return None


def insert_request(values: dict):
	active_signature = values["active_signature"]
	existing = get_pending_request(active_signature)
	if existing:
		return frappe.get_doc("Dynamic Item Request", existing.name), False

	savepoint = "dynamic_item_request_reservation"
	frappe.db.savepoint(savepoint)
	try:
		with dynamic_item_service_context():
			request = frappe.get_doc({"doctype": "Dynamic Item Request", **values})
			request.insert(ignore_permissions=True)
		return request, True
	except (frappe.DuplicateEntryError, frappe.UniqueValidationError):
		frappe.db.rollback(save_point=savepoint)
		existing = get_pending_request(active_signature)
		if not existing:
			raise
		return frappe.get_doc("Dynamic Item Request", existing.name), False


def resolve_or_request(payload) -> dict:
	require_requester()
	payload = parse_payload(payload)
	source = validate_source(payload.get("source"))
	attributes = canonicalize_known_masters(normalize_attributes(payload.get("attributes")))
	uoms = normalize_uoms(payload.get("uoms"))
	template, profile = get_template_and_profile(payload.get("template_item"))
	validate_requested_attributes(template, profile, attributes)

	identity_signature = make_identity_signature(template.name, attributes)
	existing_variant = get_variant_if_present(template.name, attributes)
	if existing_variant:
		pending_result = validate_existing_variant(existing_variant)
		if pending_result:
			return pending_result
		item = frappe.get_doc("Item", existing_variant)
		missing_uoms = get_missing_packaging(item, uoms)
		if not missing_uoms:
			return existing_result(item.name)
		return create_packaging_request(item, template, attributes, missing_uoms, source)

	return create_variant_request(template, profile, attributes, uoms, source, identity_signature)


def create_packaging_request(item, template, attributes, uoms, source) -> dict:
	require_available_approver()
	signature = make_packaging_signature(item.name, uoms)
	active_signature = f"packaging:{signature}"
	existing = get_pending_request(active_signature)
	if existing:
		return request_result(frappe.get_doc("Dynamic Item Request", existing.name))
	validate_no_overlapping_packaging_request(item.name, uoms)
	request, created = insert_request(
		{
			"request_type": ADD_PACKAGING,
			"status": PENDING,
			"template_item": template.name,
			"resolved_item": item.name,
			"signature": signature,
			"active_signature": active_signature,
			"source_doctype": source.get("doctype"),
			"source_field": source.get("fieldname"),
			"source_name": source.get("document"),
			"requested_by": frappe.session.user,
			"requested_on": now_datetime(),
			"attributes": [
				{"item_attribute": attribute, "attribute_value": value}
				for attribute, value in attributes.items()
			],
			"uoms": uoms,
		}
	)
	if created:
		request.add_comment("Info", _("Packaging addition requested for Item {0}.").format(item.name))
		assign_request_to_approvers(request)
	return request_result(request, created=created)


def validate_no_overlapping_packaging_request(item_code: str, uoms: list[dict]):
	requested_uoms = {row["uom"] for row in uoms}
	if not requested_uoms:
		return
	rows = frappe.db.sql(
		"""
		select request.name, packaging.uom
		from `tabDynamic Item Request` request
		inner join `tabDynamic Item Request UOM` packaging on packaging.parent = request.name
		where request.request_type = %(request_type)s
			and request.status = %(status)s
			and request.resolved_item = %(item_code)s
			and packaging.uom in %(uoms)s
		order by request.creation
		limit 1
		""",
		{
			"request_type": ADD_PACKAGING,
			"status": PENDING,
			"item_code": item_code,
			"uoms": tuple(requested_uoms),
		},
		as_dict=True,
	)
	if rows:
		frappe.throw(
			_("UOM {0} already has a pending packaging request {1} for Item {2}.").format(
				frappe.bold(rows[0].uom),
				frappe.get_desk_link("Dynamic Item Request", rows[0].name),
				frappe.bold(item_code),
			),
			DynamicItemConflict,
		)


def create_variant_request(template, profile, attributes, uoms, source, identity_signature) -> dict:
	require_available_approver()
	request, created = insert_request(
		{
			"request_type": CREATE_VARIANT,
			"status": PENDING,
			"template_item": template.name,
			"signature": identity_signature,
			"active_signature": f"variant:{identity_signature}",
			"source_doctype": source.get("doctype"),
			"source_field": source.get("fieldname"),
			"source_name": source.get("document"),
			"requested_by": frappe.session.user,
			"requested_on": now_datetime(),
			"attributes": [
				{"item_attribute": attribute, "attribute_value": value}
				for attribute, value in attributes.items()
			],
			"uoms": uoms,
		}
	)
	if not created:
		return request_result(request)

	lock_template(template.name)
	request = frappe.get_doc("Dynamic Item Request", request.name)
	canonical_attributes = stage_requested_schema(request, template, profile)
	request.signature = make_identity_signature(template.name, canonical_attributes)
	stage_variant_item(request, template, canonical_attributes, request.signature)
	with dynamic_item_service_context():
		request.save(ignore_permissions=True)
	request.add_comment("Info", _("Disabled Item {0} staged for approval.").format(request.staged_item_code))
	assign_request_to_approvers(request)
	return request_result(request, created=True)


def require_available_approver():
	if get_approver_users(exclude_user=frappe.session.user):
		return
	frappe.throw(
		_("No other enabled System User has the configured approver role {0}.").format(
			frappe.bold(get_settings().approver_role)
		)
	)


def assign_request_to_approvers(request):
	from frappe.desk.form.assign_to import add

	approvers = get_approver_users(exclude_user=request.requested_by)
	if not approvers:
		return
	try:
		add(
			{
				"assign_to": approvers,
				"doctype": request.doctype,
				"name": request.name,
				"description": _("Review {0} for Item template {1}.").format(
					request.request_type, request.template_item
				),
				"priority": "Medium",
				"assigned_by": request.requested_by,
			},
			ignore_permissions=True,
		)
	except Exception:
		frappe.log_error(
			title=_("Dynamic Item Approval Assignment Failed"),
			message=frappe.get_traceback(),
		)


def close_approval_assignments(request):
	from frappe.desk.form.assign_to import remove

	assignments = frappe.get_all(
		"ToDo",
		filters={
			"reference_type": request.doctype,
			"reference_name": request.name,
			"status": ["not in", ["Cancelled", "Closed"]],
		},
		pluck="allocated_to",
	)
	for user in assignments:
		remove(request.doctype, request.name, user, ignore_permissions=True)


def lock_template(template_item: str):
	frappe.db.sql("select name from `tabItem` where name = %s for update", template_item)


def stage_requested_schema(request, template, profile) -> dict[str, str]:
	canonical = {}
	profile_changed = False
	template_changed = False
	template_attributes = {row.attribute for row in template.get("attributes") or []}
	profile_attributes = {row.item_attribute for row in profile.get("attributes") or []}

	for row in request.attributes:
		attribute, attribute_created = ensure_item_attribute(row.item_attribute)
		row.item_attribute = attribute
		row.attribute_was_created = cint(attribute_created)
		value, abbreviation, value_created, master_created = ensure_attribute_value(
			attribute, row.attribute_value
		)
		row.attribute_value = value
		row.abbreviation = abbreviation
		row.value_was_created = cint(value_created)
		row.master_was_created = cint(master_created)
		canonical[attribute] = value

		if attribute not in template_attributes:
			item_attribute = frappe.get_doc("Item Attribute", attribute)
			if cint(item_attribute.numeric_values):
				frappe.throw(_("Numeric attributes must be attached to templates by a Masters manager."))
			template.append("attributes", {"attribute": attribute, "numeric_values": 0})
			template_attributes.add(attribute)
			row.template_link_was_created = 1
			template_changed = True

		if attribute not in profile_attributes:
			profile.append(
				"attributes",
				{
					"item_attribute": attribute,
					"required_parameter": 0,
					"allow_new_values": 1,
				},
			)
			profile_attributes.add(attribute)
			row.profile_row_was_created = 1
			profile_changed = True

	if template_changed:
		template.flags.dont_update_variants = True
		with dynamic_item_service_context():
			template.save(ignore_permissions=True)
	if profile_changed:
		with dynamic_item_service_context():
			profile.save(ignore_permissions=True)
	return canonical


def ensure_item_attribute(attribute: str) -> tuple[str, bool]:
	existing = get_case_insensitive_name("Item Attribute", attribute)
	if existing:
		return existing, False
	if not cint(get_settings().allow_dynamic_attributes):
		frappe.throw(_("Item Attribute {0} does not exist.").format(frappe.bold(attribute)))
	with dynamic_item_service_context():
		doc = frappe.get_doc(
			{
				"doctype": "Item Attribute",
				"attribute_name": attribute,
				"numeric_values": 0,
			}
		).insert(ignore_permissions=True)
	return doc.name, True


def ensure_attribute_value(attribute: str, value: str) -> tuple[str, str | None, bool, bool]:
	item_attribute = frappe.get_doc("Item Attribute", attribute)
	if cint(item_attribute.numeric_values):
		return value, None, False, False

	existing = get_case_insensitive_attribute_value(attribute, value)
	if existing:
		abbr = frappe.db.get_value(
			"Item Attribute Value",
			{"parent": attribute, "attribute_value": existing},
			"abbr",
		)
		return existing, abbr, False, False

	master_created = False
	if attribute.casefold() == "brand":
		brand = get_case_insensitive_name("Brand", value)
		if brand and is_brand_disabled(brand):
			frappe.throw(_("Brand {0} is disabled.").format(frappe.bold(brand)))
		if not brand:
			existing_abbrs = {
				cstr(row.abbr).casefold()
				for row in item_attribute.get("item_attribute_values") or []
				if row.abbr
			}
			abbr = make_attribute_abbr(value, existing_abbrs)
			brand_doc = {"doctype": "Brand", "brand": value}
			if frappe.db.has_column("Brand", "brand_abbreviation"):
				brand_doc["brand_abbreviation"] = abbr
			with dynamic_item_service_context():
				frappe.get_doc(brand_doc).insert(ignore_permissions=True)
			master_created = True
			brand = value
		value = brand

	existing_abbrs = {
		cstr(row.abbr).casefold() for row in item_attribute.get("item_attribute_values") or [] if row.abbr
	}
	abbr = get_brand_abbreviation(value) if attribute.casefold() == "brand" else None
	if not abbr or abbr.casefold() in existing_abbrs:
		abbr = make_attribute_abbr(value, existing_abbrs)
	item_attribute.append("item_attribute_values", {"attribute_value": value, "abbr": abbr})
	with dynamic_item_service_context():
		item_attribute.save(ignore_permissions=True)
	return value, abbr, True, master_created


def stage_variant_item(request, template, attributes: dict[str, str], identity_signature: str):
	existing = get_variant_if_present(template.name, attributes)
	if existing:
		frappe.throw(
			_("Matching Item {0} was created concurrently. Retry the request.").format(frappe.bold(existing)),
			DynamicItemConflict,
		)

	variant = create_variant(
		template.name,
		attributes,
		use_template_image=cint(get_settings().use_template_image),
	)
	if not variant.item_code:
		frappe.throw(_("ERPNext could not generate an Item Code for the requested attributes."))
	if frappe.db.exists("Item", variant.item_code):
		frappe.throw(
			_(
				"Generated Item Code {0} conflicts with a different Item. Review attribute abbreviations."
			).format(frappe.bold(variant.item_code)),
			DynamicItemConflict,
		)

	variant.disabled = 1
	variant.opening_stock = 0
	variant.standard_rate = 0
	variant.dynamic_item_approval_status = PENDING
	variant.dynamic_item_request = request.name
	variant.dynamic_variant_signature = identity_signature
	variant.dynamic_item_requested_by = request.requested_by
	add_packaging_rows(variant, [row.as_dict() for row in request.uoms])

	with dynamic_item_service_context():
		variant.insert(ignore_permissions=True)
	request.staged_item_code = variant.name


def add_packaging_rows(item, uoms: list[dict]):
	missing = get_missing_packaging(item, uoms)
	for row in missing:
		item.append(
			"uoms",
			{"uom": row["uom"], "conversion_factor": row["conversion_factor"]},
		)
	return len(missing)


def get_request_attributes(request) -> dict[str, str]:
	return {row.item_attribute: row.attribute_value for row in request.attributes}


def lock_request(name: str):
	frappe.db.sql("select name from `tabDynamic Item Request` where name = %s for update", name)


def approve_request(name: str) -> dict:
	require_approver()
	lock_request(name)
	request = frappe.get_doc("Dynamic Item Request", name)
	if request.status == APPROVED:
		return approved_result(request)
	if request.status != PENDING:
		frappe.throw(_("Only Pending Approval requests can be approved."))
	if request.requested_by == frappe.session.user:
		frappe.throw(_("Requesters cannot approve their own Dynamic Item Request."), frappe.PermissionError)

	if request.request_type == CREATE_VARIANT:
		resolved_item = approve_staged_variant(request)
	elif request.request_type == ADD_PACKAGING:
		resolved_item = approve_packaging_request(request)
	else:
		frappe.throw(_("Unsupported Dynamic Item Request type {0}.").format(request.request_type))

	request.status = APPROVED
	request.active_signature = None
	request.resolved_item = resolved_item
	request.approved_by = frappe.session.user
	request.approved_on = now_datetime()
	with dynamic_item_service_context():
		request.save(ignore_permissions=True)
	close_approval_assignments(request)
	request.add_comment("Info", _("Approved and resolved to Item {0}.").format(resolved_item))
	return approved_result(request)


def approve_staged_variant(request) -> str:
	if not request.staged_item_code or not frappe.db.exists("Item", request.staged_item_code):
		frappe.throw(_("The staged Item no longer exists."))
	lock_template(request.template_item)
	attributes = get_request_attributes(request)
	other_variant = get_variant(request.template_item, attributes, variant=request.staged_item_code)
	if other_variant:
		state = get_item_state(other_variant)
		if cint(state.disabled):
			frappe.throw(
				_("Matching Item {0} exists but is disabled.").format(frappe.bold(other_variant)),
				DynamicItemConflict,
			)
		delete_staged_item(request)
		return other_variant

	item = frappe.get_doc("Item", request.staged_item_code)
	if item.dynamic_item_approval_status != PENDING or item.dynamic_item_request != request.name:
		frappe.throw(_("Staged Item approval metadata does not match this request."))
	if not cint(item.disabled):
		frappe.throw(_("Staged Item must remain disabled until approval."))
	get_missing_packaging(item, [row.as_dict() for row in request.uoms])
	item.dynamic_item_approval_status = APPROVED
	item.dynamic_item_approved_by = frappe.session.user
	item.dynamic_item_approved_on = now_datetime()
	item.disabled = 0
	with dynamic_item_service_context():
		item.save(ignore_permissions=True)
	return item.name


def approve_packaging_request(request) -> str:
	if not request.resolved_item or not frappe.db.exists("Item", request.resolved_item):
		frappe.throw(_("The Item for this packaging request no longer exists."))
	frappe.db.sql("select name from `tabItem` where name = %s for update", request.resolved_item)
	item = frappe.get_doc("Item", request.resolved_item)
	if cint(item.disabled):
		frappe.throw(_("Item {0} is disabled.").format(frappe.bold(item.name)))
	add_packaging_rows(item, [row.as_dict() for row in request.uoms])
	with dynamic_item_service_context():
		item.save(ignore_permissions=True)
	return item.name


def approved_result(request) -> dict:
	return {
		"outcome": "approved",
		"request": request.name,
		"item_code": request.resolved_item,
		"approval_status": request.status,
	}


def reject_request(name: str, reason: str) -> dict:
	require_approver()
	reason = normalize_text(reason, _("Rejection Reason"))
	lock_request(name)
	request = frappe.get_doc("Dynamic Item Request", name)
	if request.status == REJECTED:
		return terminal_result(request)
	if request.status != PENDING:
		frappe.throw(_("Only Pending Approval requests can be rejected."))
	return terminate_request(request, REJECTED, reason, frappe.session.user)


def cancel_request(name: str, reason: str | None = None) -> dict:
	lock_request(name)
	request = frappe.get_doc("Dynamic Item Request", name)
	if request.status == CANCELLED:
		return terminal_result(request)
	if request.status != PENDING:
		frappe.throw(_("Only Pending Approval requests can be cancelled."))
	if request.requested_by != frappe.session.user and "System Manager" not in frappe.get_roles():
		frappe.throw(
			_("Only the requester or a System Manager can cancel this request."), frappe.PermissionError
		)
	return terminate_request(
		request,
		CANCELLED,
		normalize_text(reason or _("Cancelled by requester"), _("Cancellation Reason")),
		frappe.session.user,
	)


def terminate_request(request, status: str, reason: str, actor: str) -> dict:
	if request.request_type == CREATE_VARIANT:
		delete_staged_item(request)
		cleanup_request_schema(request)
	request.status = status
	request.active_signature = None
	request.rejection_reason = reason
	request.rejected_by = actor
	request.rejected_on = now_datetime()
	request.staged_item_code = None
	with dynamic_item_service_context():
		request.save(ignore_permissions=True)
	close_approval_assignments(request)
	request.add_comment("Info", _("{0}: {1}").format(status, reason))
	return terminal_result(request)


def delete_staged_item(request):
	item_code = request.staged_item_code
	if not item_code or not frappe.db.exists("Item", item_code):
		return
	links = frappe.get_all(
		"Dynamic Item Request",
		filters={"resolved_item": item_code, "name": ["!=", request.name]},
		pluck="name",
		limit=1,
	)
	if links:
		frappe.throw(_("Staged Item {0} is referenced by another request.").format(frappe.bold(item_code)))
	with dynamic_item_service_context():
		frappe.delete_doc("Item", item_code, ignore_permissions=True)


def cleanup_request_schema(request):
	for row in reversed(request.attributes):
		try:
			cleanup_attribute_artifacts(request, row)
		except Exception:
			frappe.log_error(
				title=_("Dynamic Item Schema Cleanup Failed"),
				message=frappe.get_traceback(),
			)


def cleanup_attribute_artifacts(request, row):
	attribute = row.item_attribute
	value = row.attribute_value
	history = get_request_artifact_history(request.template_item, attribute, value)
	if (
		history.template_link_created
		and not history.template_adopted
		and not attribute_used_by_other_request(request.name, request.template_item, attribute)
	):
		if not attribute_used_by_template_variant(request.template_item, attribute):
			template = frappe.get_doc("Item", request.template_item)
			template.set("attributes", [d for d in template.attributes if d.attribute != attribute])
			template.flags.dont_update_variants = True
			with dynamic_item_service_context():
				template.save(ignore_permissions=True)

	if (
		history.profile_row_created
		and not history.template_adopted
		and frappe.db.exists("Dynamic Variant Profile", request.template_item)
	):
		profile = frappe.get_doc("Dynamic Variant Profile", request.template_item)
		profile_row = next((d for d in profile.attributes if d.item_attribute == attribute), None)
		if (
			profile_row
			and not cint(profile_row.required_parameter)
			and cint(profile_row.allow_new_values)
			and not attribute_used_by_other_request(request.name, request.template_item, attribute)
		):
			profile.set("attributes", [d for d in profile.attributes if d.item_attribute != attribute])
			with dynamic_item_service_context():
				profile.save(ignore_permissions=True)

	if (
		history.value_created
		and not history.value_adopted
		and not attribute_value_is_referenced(request.name, attribute, value)
	):
		item_attribute = frappe.get_doc("Item Attribute", attribute)
		item_attribute.set(
			"item_attribute_values",
			[d for d in item_attribute.item_attribute_values if d.attribute_value != value],
		)
		with dynamic_item_service_context():
			item_attribute.save(ignore_permissions=True)

	if history.master_created and not history.value_adopted and attribute.casefold() == "brand":
		if frappe.db.exists("Brand", value) and not brand_is_referenced(value):
			with dynamic_item_service_context():
				frappe.delete_doc("Brand", value, ignore_permissions=True)

	if (
		history.attribute_created
		and not history.attribute_adopted
		and frappe.db.exists("Item Attribute", attribute)
	):
		if not frappe.db.exists("Item Variant Attribute", {"attribute": attribute}) and not frappe.db.exists(
			"Item Attribute Value", {"parent": attribute}
		):
			with dynamic_item_service_context():
				frappe.delete_doc("Item Attribute", attribute, ignore_permissions=True)


def get_request_artifact_history(template: str, attribute: str, value: str) -> frappe._dict:
	rows = frappe.db.sql(
		"""
		select
			max(attribute_row.attribute_was_created) as attribute_created,
			max(
				case when request.status = %(approved)s then 1 else 0 end
			) as attribute_adopted,
			max(
				case when request.template_item = %(template)s
				then attribute_row.template_link_was_created else 0 end
			) as template_link_created,
			max(
				case when request.template_item = %(template)s
					and request.status = %(approved)s then 1 else 0 end
			) as template_adopted,
			max(
				case when request.template_item = %(template)s
				then attribute_row.profile_row_was_created else 0 end
			) as profile_row_created,
			max(
				case when attribute_row.attribute_value = %(value)s
				then attribute_row.value_was_created else 0 end
			) as value_created,
			max(
				case when attribute_row.attribute_value = %(value)s
					and request.status = %(approved)s then 1 else 0 end
			) as value_adopted,
			max(
				case when attribute_row.attribute_value = %(value)s
				then attribute_row.master_was_created else 0 end
			) as master_created
		from `tabDynamic Item Request Attribute` attribute_row
		inner join `tabDynamic Item Request` request on request.name = attribute_row.parent
		where attribute_row.item_attribute = %(attribute)s
		""",
		{
			"approved": APPROVED,
			"template": template,
			"attribute": attribute,
			"value": value,
		},
		as_dict=True,
	)
	return frappe._dict(rows[0] if rows else {})


def attribute_used_by_template_variant(template: str, attribute: str) -> bool:
	return bool(
		frappe.db.sql(
			"""
			select 1
			from `tabItem Variant Attribute` attribute_row
			inner join `tabItem` item on item.name = attribute_row.parent
			where item.variant_of = %(template)s
				and attribute_row.attribute = %(attribute)s
			limit 1
			""",
			{"template": template, "attribute": attribute},
		)
	)


def attribute_used_by_other_request(request_name: str, template: str, attribute: str) -> bool:
	return bool(
		frappe.db.sql(
			"""
			select 1
			from `tabDynamic Item Request Attribute` attribute_row
			inner join `tabDynamic Item Request` request on request.name = attribute_row.parent
			where request.name != %(request_name)s
				and request.template_item = %(template)s
				and request.status = %(pending)s
				and attribute_row.item_attribute = %(attribute)s
			limit 1
			""",
			{
				"request_name": request_name,
				"template": template,
				"pending": PENDING,
				"attribute": attribute,
			},
		)
	)


def attribute_value_is_referenced(request_name: str, attribute: str, value: str) -> bool:
	if frappe.db.exists(
		"Item Variant Attribute",
		{"attribute": attribute, "attribute_value": value},
	):
		return True
	return bool(
		frappe.db.sql(
			"""
			select 1
			from `tabDynamic Item Request Attribute` attribute_row
			inner join `tabDynamic Item Request` request on request.name = attribute_row.parent
			where request.name != %(request_name)s
				and request.status = %(pending)s
				and attribute_row.item_attribute = %(attribute)s
				and attribute_row.attribute_value = %(value)s
			limit 1
			""",
			{
				"request_name": request_name,
				"pending": PENDING,
				"attribute": attribute,
				"value": value,
			},
		)
	)


def brand_is_referenced(brand: str) -> bool:
	if frappe.db.exists("Item", {"brand": brand}):
		return True
	return frappe.db.exists(
		"Item Variant Attribute",
		{"attribute": "Brand", "attribute_value": brand},
	)


def terminal_result(request) -> dict:
	return {
		"outcome": request.status.lower().replace(" ", "_"),
		"request": request.name,
		"item_code": request.resolved_item,
		"approval_status": request.status,
	}


def get_request_status(name: str) -> dict:
	request = frappe.get_doc("Dynamic Item Request", name)
	if request.requested_by != frappe.session.user and not (
		"System Manager" in frappe.get_roles() or user_has_approver_role()
	):
		frappe.throw(_("Not permitted to view this request."), frappe.PermissionError)
	can_review = request.status == PENDING and user_has_approver_role()
	return {
		"name": request.name,
		"request_type": request.request_type,
		"status": request.status,
		"item_code": request.resolved_item or request.staged_item_code,
		"can_approve": can_review and request.requested_by != frappe.session.user,
		"can_reject": can_review,
		"can_cancel": request.status == PENDING and request.requested_by == frappe.session.user,
	}
