from __future__ import annotations

import frappe
from erpnext.controllers.item_variant import get_variant
from frappe import _
from frappe.utils import cint

from srv_erp.masters.dynamic_item.api import build_variant_options
from srv_erp.masters.dynamic_item.brand_rule_conflicts import add_conflict, variants_for_brand
from srv_erp.masters.dynamic_item.brand_rules import get_brand_profile
from srv_erp.masters.dynamic_item.configuration import user_has_approver_role
from srv_erp.masters.dynamic_item.profile import get_template_and_profile

SYNC_LIMIT = 200


def require_backfill_manager():
	if "System Manager" not in frappe.get_roles() and not user_has_approver_role():
		frappe.throw(_("Not permitted to apply Brand defaults."), frappe.PermissionError)


@frappe.whitelist()
def preview_brand_default_backfill(brand, item_group=None, template_item=None) -> dict:
	require_backfill_manager()
	plan = build_backfill_plan(brand, item_group, template_item)
	return {
		"changes": plan["changes"],
		"conflicts": plan["conflicts"],
		"change_count": len(plan["changes"]),
		"conflict_count": len(plan["conflicts"]),
		"ignored": plan["ignored"],
	}


@frappe.whitelist()
def apply_brand_default_backfill(brand, item_group=None, template_item=None) -> dict:
	require_backfill_manager()
	plan = build_backfill_plan(brand, item_group, template_item)
	if len(plan["changes"]) > SYNC_LIMIT:
		frappe.enqueue(
			"srv_erp.masters.dynamic_item.brand_default_backfill.apply_brand_default_backfill_job",
			queue="long",
			timeout=1500,
			deduplicate=True,
			job_id=f"srv_erp:brand_default_backfill:{brand}",
			brand=brand,
			item_group=item_group,
			template_item=template_item,
		)
		return {
			"queued": 1,
			"change_count": len(plan["changes"]),
			"conflict_count": len(plan["conflicts"]),
		}
	return apply_backfill_plan(brand, item_group, template_item, plan)


def apply_brand_default_backfill_job(brand, item_group=None, template_item=None):
	plan = build_backfill_plan(brand, item_group, template_item)
	return apply_backfill_plan(brand, item_group, template_item, plan)


def build_backfill_plan(brand, item_group=None, template_item=None) -> dict:
	profile = get_brand_profile(brand)
	if not profile:
		frappe.throw(_("No Brand Variant Profile found for {0}.").format(frappe.bold(brand)))

	scope_groups = None
	if item_group:
		scope_groups = set(frappe.db.get_descendants("Item Group", item_group)) | {item_group}

	changes = []
	conflicts = []
	ignored = []
	template_cache = {}

	for item_code, variant in variants_for_brand(brand).items():
		template_name = variant["template"]
		if not template_name or (template_item and template_name != template_item):
			continue
		if template_name not in template_cache:
			template_cache[template_name] = get_template_and_profile(template_name)
		template, dynamic_profile = template_cache[template_name]
		if scope_groups is not None and template.item_group not in scope_groups:
			continue

		options = build_variant_options(template, dynamic_profile, brand)
		for entry in options.get("default_ignored") or []:
			ignored.append({"template_item": template_name, **entry})

		defaults = {
			attribute["attribute"]: attribute["default"]
			for attribute in options["attributes"]
			if "default" in attribute
		}
		existing = variant["attributes"]
		missing = {attribute: value for attribute, value in defaults.items() if not existing.get(attribute)}
		if not missing:
			continue

		proposed = {**existing, **missing}
		collision = get_variant(template_name, proposed, item_code)
		if collision:
			conflicts.append(
				{
					"item_code": item_code,
					"template_item": template_name,
					"attribute": "",
					"value": "",
					"reason": _("Variant {0} already has this combination.").format(collision),
				}
			)
			continue

		changes.append(
			{
				"item_code": item_code,
				"template_item": template_name,
				"attributes": missing,
			}
		)

	return {"changes": changes, "conflicts": conflicts, "ignored": ignored}


def apply_backfill_plan(brand, item_group, template_item, plan) -> dict:
	profile = get_brand_profile(brand)
	revision = cint(profile.published_revision) if profile else 0
	applied = 0
	failed = 0

	for index, change in enumerate(plan["changes"], start=1):
		item_code = change["item_code"]
		savepoint = f"brand_default_backfill_{index}"
		frappe.db.savepoint(savepoint)
		try:
			item = frappe.get_doc("Item", item_code)
			current = {row.attribute for row in item.get("attributes") or [] if row.attribute}
			added = 0
			for attribute, value in change["attributes"].items():
				if attribute in current:
					continue
				item.append(
					"attributes",
					{
						"attribute": attribute,
						"attribute_value": value,
						"variant_of": item.variant_of,
					},
				)
				current.add(attribute)
				added += 1
			if not added:
				continue
			item.save(ignore_permissions=True)
			applied += added
		except Exception:
			frappe.db.rollback(save_point=savepoint)
			frappe.log_error(frappe.get_traceback(), "Brand Default Backfill")
			if profile:
				add_conflict(
					profile,
					revision,
					"Default Backfill Failed",
					change["template_item"],
					next(iter(change["attributes"]), None),
					item_code,
					next(iter(change["attributes"].values()), None),
					details=_("The variant could not be updated; inspect the Error Log."),
				)
			failed += 1

	for conflict in plan["conflicts"]:
		if profile:
			add_conflict(
				profile,
				revision,
				"Default Backfill Conflict",
				conflict["template_item"],
				conflict["attribute"] or None,
				conflict["item_code"],
				conflict["value"] or None,
				details=conflict["reason"],
			)

	return {
		"applied": applied,
		"failed": failed,
		"change_count": len(plan["changes"]),
		"conflict_count": len(plan["conflicts"]),
		"ignored": plan["ignored"],
	}
