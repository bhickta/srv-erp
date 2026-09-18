from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from srv_erp.masters.dynamic_item.brand_rule_conflicts import (
	add_conflict,
	audit_existing_variants,
	resolve_open_conflicts,
)
from srv_erp.masters.dynamic_item.brand_rules import get_published_configuration, is_numeric_attribute
from srv_erp.masters.dynamic_item.configuration import are_brand_variant_rules_enabled


def enqueue_brand_rule_sync(profile_name: str, revision: int, previous_configuration=None):
	frappe.enqueue(
		"srv_erp.masters.dynamic_item.brand_rule_sync.sync_brand_rule_revision",
		queue="long",
		timeout=1500,
		enqueue_after_commit=True,
		deduplicate=True,
		job_id=f"srv_erp:brand_rule_sync:{profile_name}:{revision}",
		profile_name=profile_name,
		revision=cint(revision),
		previous_configuration=previous_configuration,
	)


def sync_brand_rule_revision(profile_name: str, revision: int, previous_configuration=None):
	try:
		return _sync_brand_rule_revision(profile_name, revision, previous_configuration)
	except Exception:
		profile = frappe.get_doc("Brand Variant Profile", profile_name)
		if cint(profile.published_revision) == cint(revision):
			set_status(profile, "Failed", _("Synchronization failed; inspect the Error Log and retry."))
		frappe.log_error(frappe.get_traceback(), "Brand Variant Rule Sync")
		raise


def _sync_brand_rule_revision(profile_name: str, revision: int, previous_configuration=None):
	profile = frappe.get_doc("Brand Variant Profile", profile_name)
	if not are_brand_variant_rules_enabled():
		set_status(profile, "Disabled", _("Feature was disabled before synchronization."))
		return {"disabled": 1}
	if cint(profile.published_revision) != cint(revision):
		return {"stale": 1}
	configuration = get_published_configuration(profile)
	if not configuration:
		set_status(profile, "Failed", _("Published configuration is unavailable."))
		return {"failed": 1}

	if previous_configuration is None:
		previous_configuration = json.loads(profile.get("previous_configuration") or '{"attributes":[]}')
	set_status(profile, "Running", _("Synchronizing revision {0}.").format(revision))
	resolve_open_conflicts(profile)
	conflicts = sync_template_schemas(profile, configuration, revision)
	if not still_current(profile.name, revision):
		return {"stale": 1, "conflicts": conflicts}
	conflicts += audit_existing_variants(
		profile,
		configuration,
		revision,
		previous_configuration or {"attributes": []},
	)
	profile.reload()
	if cint(profile.published_revision) != cint(revision) or not are_brand_variant_rules_enabled():
		return {"stale": 1, "conflicts": conflicts}
	profile.db_set(
		{
			"sync_status": "Completed with Conflicts" if conflicts else "Completed",
			"last_synced_revision": revision,
			"last_sync_on": now_datetime(),
			"last_sync_message": _("Synchronization completed with {0} conflict(s).").format(conflicts),
		},
		update_modified=False,
	)
	return {"conflicts": conflicts, "revision": revision}


def brand_templates() -> list[str]:
	return frappe.db.sql_list(
		"""
		select distinct attribute.parent
		from `tabItem Variant Attribute` attribute
		inner join `tabItem` item on item.name = attribute.parent
		where attribute.attribute = 'Brand'
			and item.has_variants = 1
			and item.variant_based_on = 'Item Attribute'
		order by attribute.parent
		"""
	)


def sync_template_schemas(profile, configuration, revision) -> int:
	conflicts = 0
	for index, template_name in enumerate(brand_templates(), start=1):
		if not still_current(profile.name, revision):
			break
		template = frappe.get_doc("Item", template_name)
		existing = {row.attribute for row in template.get("attributes") or []}
		changed = False
		for rule in configuration.get("attributes", []):
			attribute = rule.get("attribute")
			if not attribute or attribute in existing:
				continue
			if is_numeric_attribute(attribute):
				add_conflict(
					profile,
					revision,
					"Numeric Range Required",
					template_name,
					attribute,
					details=_("Configure the numeric range on this Item template manually."),
				)
				conflicts += 1
				continue
			template.append("attributes", {"attribute": attribute, "numeric_values": 0})
			existing.add(attribute)
			changed = True
		if not changed:
			continue
		savepoint = f"brand_rule_template_{index}"
		frappe.db.savepoint(savepoint)
		try:
			template.flags.dont_update_variants = True
			template.save(ignore_permissions=True)
		except Exception:
			frappe.db.rollback(save_point=savepoint)
			frappe.log_error(frappe.get_traceback(), "Brand Variant Rule Template Sync")
			add_conflict(
				profile,
				revision,
				"Template Schema Sync Failed",
				template_name,
				details=_("The template could not be updated; inspect the Error Log."),
			)
			conflicts += 1
	return conflicts


def still_current(profile_name, revision) -> bool:
	return are_brand_variant_rules_enabled() and cint(
		frappe.db.get_value("Brand Variant Profile", profile_name, "published_revision")
	) == cint(revision)


def set_status(profile, status, message):
	profile.db_set(
		{"sync_status": status, "last_sync_on": now_datetime(), "last_sync_message": message},
		update_modified=False,
	)
