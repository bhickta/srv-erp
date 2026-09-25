from __future__ import annotations

import hashlib
import json

import frappe
from erpnext.controllers.item_variant import get_variant
from frappe import _
from frappe.utils import add_to_date, cint, now_datetime

from srv_erp.item.variant_auto_creation import is_brand_disabled
from srv_erp.masters.dynamic_item.brand_rule_resolution import resolve_effective_rules
from srv_erp.masters.dynamic_item.brand_rules import (
	get_brand_profile,
	get_published_configuration,
	resolve_published_item_group_defaults,
)
from srv_erp.masters.dynamic_item.configuration import are_brand_variant_rules_enabled, user_has_approver_role


def require_manager():
	if "System Manager" not in frappe.get_roles() and not user_has_approver_role():
		frappe.throw(_("Not permitted to synchronize Brand variant values."), frappe.PermissionError)


def _attributes(item):
	return {row.attribute: row.attribute_value or "" for row in item.get("attributes") or [] if row.attribute}


def _fingerprint(item, template):
	payload = [
		item.modified,
		_attributes(item),
		template.modified,
		template.item_group,
		[row.as_dict() for row in template.get("attributes") or []],
	]
	return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def assigned_changes(before, defaults, mode):
	proposed = dict(before)
	changes = {}
	for attribute, assignment in defaults.items():
		value = assignment["value"]
		old = before.get(attribute)
		if old == value or (old and mode == "Fill Missing"):
			continue
		proposed[attribute] = value
		changes[attribute] = {"old": old, "new": value, "source_group": assignment["source_group"]}
	return proposed, changes


def _eligible_items(brand, item_group=None, template_item=None):
	conditions = [
		"i.disabled = 0",
		"t.disabled = 0",
		"i.has_variants = 0",
		"i.variant_of is not null",
		"i.variant_based_on = 'Item Attribute'",
		"a.attribute = 'Brand'",
		"lower(a.attribute_value) = lower(%(brand)s)",
	]
	args = {"brand": brand}
	if template_item:
		conditions.append("i.variant_of = %(template_item)s")
		args["template_item"] = template_item
	if item_group:
		groups = set(frappe.get_all("Item Group", filters={"parent_item_group": item_group}, pluck="name"))
		groups.add(item_group)
		groups.update(frappe.db.get_descendants("Item Group", item_group) or [])
		conditions.append("t.item_group in %(groups)s")
		conditions[-1] = "t.item_group in %(groups)s"
		args = {"brand": brand, "groups": tuple(groups)}
		if template_item:
			args["template_item"] = template_item
		where = " and ".join(conditions)
		return frappe.db.sql(
			f"""select distinct i.name from `tabItem` i join `tabItem Variant Attribute` a on a.parent=i.name and a.parenttype='Item' and a.parentfield='attributes' join `tabItem` t on t.name=i.variant_of where {where} order by i.name limit 501""",
			args,
			pluck=True,
		)
	where = " and ".join(conditions)
	return frappe.db.sql(
		f"""select distinct i.name from `tabItem` i join `tabItem Variant Attribute` a on a.parent=i.name and a.parenttype='Item' and a.parentfield='attributes' join `tabItem` t on t.name=i.variant_of where {where} order by i.name limit 501""",
		args,
		pluck=True,
	)


def _effective_rules(template, brand):
	from srv_erp.masters.dynamic_item.profile import get_dynamic_variant_profile_name

	name = get_dynamic_variant_profile_name(template.name)
	profile = (
		frappe.get_doc("Dynamic Variant Profile", name)
		if name
		else frappe._dict(attributes=[], configuration_mode="Inherit Brand Rules")
	)
	if name and not cint(profile.enabled):
		frappe.throw(_("Dynamic Variant Profile is disabled for {0}.").format(template.name))
	if (profile.get("configuration_mode") or "Inherit Brand Rules") == "Template Override":
		frappe.throw(_("Template Override profiles are not included in Brand value synchronization."))
	return resolve_effective_rules(template, profile, brand)["configuration"]


def _preview(brand, item_group, template_item, mode, configuration):
	from srv_erp.masters.dynamic_item.api import (
		_attribute_option,
		_template_attribute_rows,
		invalid_default_reason,
	)

	items = _eligible_items(brand, item_group, template_item)
	if len(items) > 500:
		frappe.throw(_("Preview is limited to 500 variants. Narrow the Item Group or template filter."))
	rows = []
	template_cache = {}
	for item_code in items:
		item = frappe.get_doc("Item", item_code)
		if not item.has_permission("read"):
			continue
		before = _attributes(item)
		entry = {
			"item_code": item.name,
			"template_item": item.variant_of,
			"before_values": json.dumps(before, sort_keys=True),
			"after_values": json.dumps(before, sort_keys=True),
			"changes": "{}",
			"fingerprint": "",
		}
		try:
			brand_rows = [row for row in item.attributes if (row.attribute or "").casefold() == "brand"]
			if len(brand_rows) != 1 or len(before) != len([row for row in item.attributes if row.attribute]):
				entry.update(
					status="Conflict", reason=_("Variant has duplicate or malformed attribute rows.")
				)
				rows.append(entry)
				continue
			if item.variant_of not in template_cache:
				template_cache[item.variant_of] = frappe.get_doc("Item", item.variant_of)
			template = template_cache[item.variant_of]
			entry["fingerprint"] = _fingerprint(item, template)
			if item.brand and item.brand.casefold() != brand.casefold():
				entry.update(
					status="Conflict",
					reason=_("Item Brand field conflicts with the Brand variant attribute."),
				)
				rows.append(entry)
				continue
			if (
				template.disabled
				or not template.has_variants
				or template.variant_based_on != "Item Attribute"
			):
				entry.update(
					status="Skipped", reason=_("Template is disabled or is not an Item Attribute template.")
				)
				rows.append(entry)
				continue
			if item.item_group != template.item_group:
				entry.update(status="Skipped", reason=_("Variant Item Group differs from its template."))
				rows.append(entry)
				continue
			defaults = resolve_published_item_group_defaults(configuration, template.item_group)
			template_rows = _template_attribute_rows(template)
			rules = {r["attribute"]: r for r in _effective_rules(template, brand).get("attributes", [])}
			proposed, changes = assigned_changes(before, defaults, mode)
			problem = None
			for attribute, assignment in defaults.items():
				value = assignment["value"]
				row = template_rows.get(attribute)
				if not row:
					problem = _("Attribute {0} is not enabled on the template.").format(attribute)
					break
				option = _attribute_option(attribute, row)
				reason = invalid_default_reason(option, value)
				if not reason and option.get("numeric_values"):
					from srv_erp.masters.dynamic_item.profile import validate_numeric_value

					try:
						validate_numeric_value(template.name, attribute, value)
					except frappe.ValidationError as exc:
						reason = frappe.utils.strip_html(str(exc))
				allowed = rules.get(attribute, {}).get("values") or []
				if not reason and allowed and value.casefold() not in {v.casefold() for v in allowed}:
					reason = _("Value {0} is not allowed by the published Brand rules.").format(value)
				if reason:
					problem = reason
					break
			if problem:
				entry.update(status="Conflict", reason=problem)
			elif any(rule.get("required") and not proposed.get(name) for name, rule in rules.items()):
				entry.update(
					status="Conflict", reason=_("The proposed values leave a required attribute empty.")
				)
			elif any(
				proposed.get(name)
				and rule.get("values")
				and proposed[name].casefold() not in {value.casefold() for value in rule["values"]}
				for name, rule in rules.items()
			):
				entry.update(
					status="Conflict",
					reason=_("The proposed values conflict with the published Brand rules."),
				)
			elif not changes:
				entry.update(status="Unchanged", reason=_("Values already match."))
			else:
				collision = get_variant(item.variant_of, proposed, item.name)
				if collision:
					entry.update(
						status="Conflict",
						reason=_("Variant {0} already has this attribute combination.").format(collision),
					)
				else:
					entry.update(
						status="Planned",
						after_values=json.dumps(proposed, sort_keys=True),
						changes=json.dumps(changes, sort_keys=True),
					)
		except Exception as exc:
			entry.update(status="Skipped", reason=frappe.utils.strip_html(str(exc)))
		rows.append(entry)
	planned_by_target = {}
	for entry in rows:
		if entry.get("status") != "Planned":
			continue
		target = (entry["template_item"], entry["after_values"])
		planned_by_target.setdefault(target, []).append(entry)
	for matching in planned_by_target.values():
		if len(matching) > 1:
			for entry in matching:
				entry.update(
					status="Conflict",
					reason=_("Multiple variants would have the same attribute combination."),
				)
	return rows


@frappe.whitelist()
def preview_brand_variant_value_sync(brand, item_group=None, template_item=None, mode="Synchronize"):
	require_manager()
	if not are_brand_variant_rules_enabled():
		frappe.throw(_("Enable Brand Variant Rules before synchronizing."))
	if mode not in ("Synchronize", "Fill Missing"):
		frappe.throw(_("Invalid synchronization mode."))
	if not frappe.db.exists("Brand", brand):
		frappe.throw(_("Select an existing Brand."))
	brand_doc = frappe.get_doc("Brand", brand)
	if not brand_doc.has_permission("read") or is_brand_disabled(brand):
		frappe.throw(
			_("Brand is unavailable or you do not have permission to read it."), frappe.PermissionError
		)
	if not brand_doc.has_permission("write"):
		frappe.throw(_("Not permitted to synchronize values for this Brand."), frappe.PermissionError)
	if item_group and not frappe.db.exists("Item Group", item_group):
		frappe.throw(_("Select an existing Item Group."))
	if template_item:
		template_doc = frappe.get_doc("Item", template_item)
		if (
			not template_doc.has_permission("read")
			or not template_doc.has_variants
			or template_doc.variant_based_on != "Item Attribute"
		):
			frappe.throw(_("Select a readable Item Attribute template."), frappe.PermissionError)
	profile = get_brand_profile(brand)
	configuration = get_published_configuration(profile)
	if not profile or not configuration:
		frappe.throw(_("Publish Brand rules and Item Group values before synchronization."))
	if not configuration.get("item_group_defaults"):
		frappe.throw(_("No published Item Group attribute values are configured for this Brand."))
	rows = _preview(brand, item_group, template_item, mode, configuration)
	run = frappe.get_doc(
		{
			"doctype": "Brand Variant Value Sync Run",
			"brand": brand,
			"profile": profile.name,
			"revision": cint(profile.published_revision),
			"configuration_hash": hashlib.sha256(
				json.dumps(configuration, sort_keys=True).encode()
			).hexdigest(),
			"requested_by": frappe.session.user,
			"item_group": item_group,
			"template_item": template_item,
			"mode": mode,
			"status": "Preview Ready",
			"preview_expires_on": add_to_date(now_datetime(), minutes=30),
			"candidate_count": len(rows),
			"changed_variant_count": sum(r["status"] == "Planned" for r in rows),
			"changed_attribute_count": sum(
				len(json.loads(r["changes"])) for r in rows if r["status"] == "Planned"
			),
			"conflict_count": sum(r["status"] == "Conflict" for r in rows),
			"skipped_count": sum(r["status"] == "Skipped" for r in rows),
			"results": rows,
		}
	)
	run.insert(ignore_permissions=True)
	return {
		"run": run.name,
		"status": run.status,
		"candidate_count": run.candidate_count,
		"changed_variant_count": run.changed_variant_count,
		"changed_attribute_count": run.changed_attribute_count,
		"conflict_count": run.conflict_count,
		"skipped_count": run.skipped_count,
		"results": rows,
	}


@frappe.whitelist()
def get_brand_variant_value_sync_run(run):
	require_manager()
	doc = frappe.get_doc("Brand Variant Value Sync Run", run)
	if not frappe.get_doc("Brand", doc.brand).has_permission("read"):
		frappe.throw(_("Not permitted to read this Brand synchronization run."), frappe.PermissionError)
	data = doc.as_dict()
	data["results"] = [
		row
		for row in data.get("results", [])
		if frappe.db.exists("Item", row["item_code"])
		and frappe.get_doc("Item", row["item_code"]).has_permission("read")
	]
	return data


@frappe.whitelist()
def apply_brand_variant_value_sync(run):
	require_manager()
	frappe.db.sql("select name from `tabBrand Variant Value Sync Run` where name = %s for update", (run,))
	doc = frappe.get_doc("Brand Variant Value Sync Run", run)
	if doc.status != "Preview Ready" or doc.preview_expires_on < now_datetime():
		frappe.throw(_("This preview expired or was already applied. Create a new preview."))
	if doc.requested_by != frappe.session.user and "System Manager" not in frappe.get_roles():
		frappe.throw(
			_("Only the requester or a System Manager can apply this preview."), frappe.PermissionError
		)
	doc.applied_by = frappe.session.user
	if sum(row.status == "Planned" for row in doc.results) > 50:
		doc.status = "Queued"
		doc.save(ignore_permissions=True)
		frappe.enqueue(
			"srv_erp.masters.dynamic_item.brand_value_sync.apply_brand_variant_value_sync_job",
			run=doc.name,
			queue="long",
			timeout=1500,
			enqueue_after_commit=True,
			deduplicate=True,
			job_id=f"srv_erp:brand_value_sync:{doc.name}",
		)
		return {"run": doc.name, "status": "Queued"}
	return _execute_brand_variant_value_sync(doc.name, "Preview Ready")


def apply_brand_variant_value_sync_job(run):
	return _execute_brand_variant_value_sync(run, "Queued")


def _execute_brand_variant_value_sync(run, expected_status):
	frappe.db.sql("select name from `tabBrand Variant Value Sync Run` where name = %s for update", (run,))
	doc = frappe.get_doc("Brand Variant Value Sync Run", run)
	if doc.status != expected_status:
		return {"run": doc.name, "status": doc.status}
	if doc.preview_expires_on < now_datetime():
		doc.status = "Stale"
		doc.save(ignore_permissions=True)
		return {"run": doc.name, "status": "Stale", "message": _("Preview expired. Create a new preview.")}
	old_user = frappe.session.user
	frappe.set_user(doc.applied_by or doc.requested_by)
	try:
		require_manager()
		brand_doc = frappe.get_doc("Brand", doc.brand)
		if not brand_doc.has_permission("write") or is_brand_disabled(doc.brand):
			doc.status = "Stale"
			doc.message = _("Brand is unavailable or permission changed since preview.")
			doc.save(ignore_permissions=True)
			return {"run": doc.name, "status": doc.status, "message": doc.message}
		if doc.requested_by != frappe.session.user and "System Manager" not in frappe.get_roles():
			frappe.throw(
				_("Only the requester or a System Manager can apply this preview."), frappe.PermissionError
			)
		profile = get_brand_profile(doc.brand)
		if not profile:
			doc.status = "Stale"
			doc.save(ignore_permissions=True)
			return {"run": doc.name, "status": "Stale"}
		frappe.db.sql(
			"select name from `tabBrand Variant Profile` where name = %s for update", (profile.name,)
		)
		profile.reload()
		configuration = get_published_configuration(profile)
		current_hash = hashlib.sha256(json.dumps(configuration or {}, sort_keys=True).encode()).hexdigest()
		if (
			not configuration
			or cint(profile.published_revision) != cint(doc.revision)
			or current_hash != doc.configuration_hash
		):
			doc.status = "Stale"
			doc.save(ignore_permissions=True)
			return {
				"run": doc.name,
				"status": "Stale",
				"message": _("Published Brand configuration changed. Create a new preview."),
			}
		doc.status = "Running"
		doc.save(ignore_permissions=True)
		for row in doc.results:
			if row.status != "Planned":
				continue
			point = f"brand_sync_{row.idx}"
			frappe.db.savepoint(point)
			try:
				item = frappe.get_doc("Item", row.item_code)
				if not item.has_permission("write"):
					row.status = "Skipped"
					row.reason = _("No write permission on Item.")
					continue
				template = frappe.get_doc("Item", item.variant_of)
				if _fingerprint(item, template) != row.fingerprint:
					row.status = "Conflict"
					row.reason = _("Item or template changed since preview.")
					continue
				proposed = json.loads(row.after_values)
				current_defaults = resolve_published_item_group_defaults(configuration, template.item_group)
				planned_changes = json.loads(row.changes)
				if any(
					attribute not in current_defaults
					or current_defaults[attribute]["value"] != change["new"]
					or current_defaults[attribute]["source_group"] != change["source_group"]
					for attribute, change in planned_changes.items()
				):
					row.status = "Conflict"
					row.reason = _("Item Group assignment changed since preview.")
					continue
				collision = get_variant(item.variant_of, proposed, item.name)
				if collision:
					row.status = "Conflict"
					row.reason = _("Variant {0} now has this attribute combination.").format(collision)
					continue
				by_name = {r.attribute: r for r in item.attributes if r.attribute}
				for attr, value in proposed.items():
					if attr in by_name and by_name[attr].attribute_value != value:
						by_name[attr].attribute_value = value
					elif attr not in by_name:
						item.append(
							"attributes",
							{"attribute": attr, "attribute_value": value, "variant_of": item.variant_of},
						)
				item.save()
				row.status = "Applied"
			except Exception:
				frappe.db.rollback(save_point=point)
				row.status = "Failed"
				row.reason = _("Item could not be saved; inspect Error Log.")
				frappe.log_error(frappe.get_traceback(), "Brand Variant Value Sync")
			doc.save(ignore_permissions=True)
		doc.status = (
			"Completed with Conflicts"
			if any(r.status in ("Conflict", "Failed", "Skipped") for r in doc.results)
			else "Completed"
		)
		doc.save(ignore_permissions=True)
		return {
			"run": doc.name,
			"status": doc.status,
			"applied": sum(r.status == "Applied" for r in doc.results),
		}
	finally:
		frappe.set_user(old_user)
