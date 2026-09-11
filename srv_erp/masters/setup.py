from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from srv_erp.masters.dynamic_item.configuration import APPROVER_ROLE, REQUESTER_ROLE, clear_settings_cache

SYSTEM_MANAGER_ROLE = "System Manager"


def ensure_masters_roles():
	for role_name in (REQUESTER_ROLE, APPROVER_ROLE):
		if not frappe.db.exists("Role", role_name):
			frappe.get_doc(
				{
					"doctype": "Role",
					"role_name": role_name,
					"desk_access": 1,
				}
			).insert(ignore_permissions=True)


def provision_masters_user_roles() -> dict[str, int]:
	"""Make the approval workflow usable without manual user-role setup.

	Every enabled Desk user may request an Item. Approval stays restricted to
	System Managers, and at least two are required so a manager can never strand
	their own request under the maker-checker rule.
	"""
	ensure_masters_roles()
	system_users = frappe.get_all(
		"User",
		filters={"enabled": 1, "user_type": "System User"},
		pluck="name",
		order_by="name",
	)
	system_user_set = set(system_users)
	system_managers = sorted(
		set(
			frappe.get_all(
				"Has Role",
				filters={"role": SYSTEM_MANAGER_ROLE, "parenttype": "User"},
				pluck="parent",
			)
		).intersection(system_user_set)
	)
	manager_set = set(system_managers)
	for user_name in system_users:
		roles = [REQUESTER_ROLE]
		if user_name in manager_set:
			roles.append(APPROVER_ROLE)
		frappe.get_doc("User", user_name).add_roles(*roles)

	return {"requesters": len(system_users), "approvers": len(system_managers)}


def activate_dynamic_item_creation() -> dict[str, int]:
	"""Provision and enable the production-safe dynamic Item workflow."""
	setup_masters_module()
	role_counts = provision_masters_user_roles()
	settings = frappe.get_single("Masters Settings")
	approvals_ready = role_counts["approvers"] >= 2
	settings.enable_dynamic_item_requests = int(approvals_ready)
	settings.enforce_variant_approval = int(approvals_ready)
	settings.allow_bulk_variant_creation = 0
	settings.allow_dynamic_attributes = 0
	settings.save(ignore_permissions=True)
	frappe.db.set_single_value("SRV Settings", "auto_create_variants_on_brand_update", 0)
	clear_settings_cache()
	return role_counts


def create_dynamic_item_custom_fields():
	create_custom_fields(
		{
			"Item": [
				{
					"fieldname": "dynamic_item_approval_section",
					"fieldtype": "Section Break",
					"insert_after": "disabled",
					"label": "Dynamic Item Approval",
					"collapsible": 1,
				},
				{
					"fieldname": "dynamic_item_approval_status",
					"fieldtype": "Select",
					"insert_after": "dynamic_item_approval_section",
					"label": "Dynamic Item Approval Status",
					"options": "\nPending Approval\nApproved",
					"read_only": 1,
					"in_list_view": 1,
					"in_standard_filter": 1,
				},
				{
					"fieldname": "dynamic_item_request",
					"fieldtype": "Link",
					"insert_after": "dynamic_item_approval_status",
					"label": "Dynamic Item Request",
					"options": "Dynamic Item Request",
					"read_only": 1,
					"in_standard_filter": 1,
				},
				{
					"fieldname": "dynamic_variant_signature",
					"fieldtype": "Data",
					"insert_after": "dynamic_item_request",
					"label": "Dynamic Variant Signature",
					"read_only": 1,
					"unique": 1,
					"hidden": 1,
				},
				{
					"fieldname": "dynamic_item_requested_by",
					"fieldtype": "Link",
					"insert_after": "dynamic_variant_signature",
					"label": "Dynamic Item Requested By",
					"options": "User",
					"read_only": 1,
				},
				{
					"fieldname": "dynamic_item_approved_by",
					"fieldtype": "Link",
					"insert_after": "dynamic_item_requested_by",
					"label": "Dynamic Item Approved By",
					"options": "User",
					"read_only": 1,
				},
				{
					"fieldname": "dynamic_item_approved_on",
					"fieldtype": "Datetime",
					"insert_after": "dynamic_item_approved_by",
					"label": "Dynamic Item Approved On",
					"read_only": 1,
				},
			],
		},
		update=True,
	)


def set_masters_settings_defaults():
	if not frappe.db.exists("DocType", "Masters Settings"):
		return

	settings = frappe.get_single("Masters Settings")
	changed = False
	defaults = {
		"enable_dynamic_item_requests": 0,
		"enforce_variant_approval": 1,
		"allow_bulk_variant_creation": 0,
		"allow_dynamic_attributes": 0,
		"use_template_image": 0,
		"approver_role": APPROVER_ROLE,
	}
	for fieldname, value in defaults.items():
		if settings.get(fieldname) is None or (fieldname == "approver_role" and not settings.get(fieldname)):
			settings.set(fieldname, value)
			changed = True

	if not settings.get("requester_roles"):
		settings.append("requester_roles", {"role": REQUESTER_ROLE})
		changed = True

	if changed:
		settings.save(ignore_permissions=True)
	clear_settings_cache()


def bootstrap_dynamic_variant_profiles():
	if not frappe.db.exists("DocType", "Dynamic Variant Profile"):
		return 0

	created = 0
	for template in frappe.get_all(
		"Item",
		filters={"has_variants": 1, "variant_based_on": "Item Attribute"},
		pluck="name",
		order_by="name",
	):
		if frappe.db.exists("Dynamic Variant Profile", template):
			continue

		profile = frappe.get_doc(
			{
				"doctype": "Dynamic Variant Profile",
				"item_template": template,
				"enabled": 1,
			}
		)
		for attribute in frappe.get_all(
			"Item Variant Attribute",
			filters={"parent": template},
			pluck="attribute",
			order_by="idx",
		):
			profile.append(
				"attributes",
				{
					"item_attribute": attribute,
					"required_parameter": 0,
					"allow_new_values": 0,
				},
			)
		profile.insert(ignore_permissions=True)
		created += 1
	return created


def sync_dynamic_item_grids():
	if not frappe.db.exists("DocType", "Masters Settings"):
		return 0

	settings = frappe.get_single("Masters Settings")
	existing = {(row.document_type, row.table_field) for row in settings.get("item_grids") or []}
	added = 0

	for document_type in frappe.get_all(
		"DocType",
		filters={"istable": 0, "issingle": 0},
		pluck="name",
		order_by="name",
	):
		meta = frappe.get_meta(document_type)
		for table_field in meta.fields:
			if table_field.fieldtype != "Table" or table_field.read_only or table_field.hidden:
				continue
			if not table_field.options or not frappe.db.exists("DocType", table_field.options):
				continue
			item_field = frappe.get_meta(table_field.options).get_field("item_code")
			if not item_field or item_field.fieldtype != "Link" or item_field.options != "Item":
				continue
			if item_field.read_only or item_field.hidden:
				continue
			key = (document_type, table_field.fieldname)
			if key in existing:
				continue
			settings.append(
				"item_grids",
				{
					"enabled": 1,
					"document_type": document_type,
					"table_field": table_field.fieldname,
					"child_doctype": table_field.options,
				},
			)
			existing.add(key)
			added += 1

	if added:
		settings.save(ignore_permissions=True)
	clear_settings_cache()
	return added


def setup_masters_module():
	ensure_masters_roles()
	create_dynamic_item_custom_fields()
	set_masters_settings_defaults()
	bootstrap_dynamic_variant_profiles()
	sync_dynamic_item_grids()
