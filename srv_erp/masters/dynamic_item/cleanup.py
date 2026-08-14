import frappe
from frappe import _
from frappe.utils import cint

from srv_erp.masters.dynamic_item.artifact_usage import (
	attribute_used_by_other_request,
	attribute_used_by_template_variant,
	attribute_value_is_referenced,
	brand_is_referenced,
	get_request_artifact_history,
)
from srv_erp.masters.dynamic_item.context import dynamic_item_service_context


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
	used_by_other_request = attribute_used_by_other_request(request.name, request.template_item, attribute)
	value_is_referenced = attribute_value_is_referenced(request.name, attribute, value)

	cleanup_template_link(request.template_item, attribute, history, used_by_other_request)
	cleanup_profile_row(request.template_item, attribute, history, used_by_other_request)
	cleanup_attribute_value(attribute, value, history, value_is_referenced)
	cleanup_brand(attribute, value, history)
	cleanup_item_attribute(attribute, history)


def cleanup_template_link(template_name, attribute, history, used_by_other_request):
	if not history.template_link_created or history.template_adopted or used_by_other_request:
		return
	if attribute_used_by_template_variant(template_name, attribute):
		return
	template = frappe.get_doc("Item", template_name)
	template.set("attributes", [d for d in template.attributes if d.attribute != attribute])
	template.flags.dont_update_variants = True
	with dynamic_item_service_context():
		template.save(ignore_permissions=True)


def cleanup_profile_row(template_name, attribute, history, used_by_other_request):
	if (
		not history.profile_row_created
		or history.template_adopted
		or used_by_other_request
		or not frappe.db.exists("Dynamic Variant Profile", template_name)
	):
		return
	profile = frappe.get_doc("Dynamic Variant Profile", template_name)
	profile_row = next((d for d in profile.attributes if d.item_attribute == attribute), None)
	if not profile_row or cint(profile_row.required_parameter) or not cint(profile_row.allow_new_values):
		return
	profile.set("attributes", [d for d in profile.attributes if d.item_attribute != attribute])
	with dynamic_item_service_context():
		profile.save(ignore_permissions=True)


def cleanup_attribute_value(attribute, value, history, value_is_referenced):
	if not history.value_created or history.value_adopted or value_is_referenced:
		return
	item_attribute = frappe.get_doc("Item Attribute", attribute)
	item_attribute.set(
		"item_attribute_values",
		[d for d in item_attribute.item_attribute_values if d.attribute_value != value],
	)
	with dynamic_item_service_context():
		item_attribute.save(ignore_permissions=True)


def cleanup_brand(attribute, value, history):
	if not history.master_created or history.value_adopted or attribute.casefold() != "brand":
		return
	if frappe.db.exists("Brand", value) and not brand_is_referenced(value):
		with dynamic_item_service_context():
			frappe.delete_doc("Brand", value, ignore_permissions=True)


def cleanup_item_attribute(attribute, history):
	if history.attribute_adopted or not history.attribute_created:
		return
	if not frappe.db.exists("Item Attribute", attribute):
		return
	if frappe.db.exists("Item Variant Attribute", {"attribute": attribute}):
		return
	if frappe.db.exists("Item Attribute Value", {"parent": attribute}):
		return
	with dynamic_item_service_context():
		frappe.delete_doc("Item Attribute", attribute, ignore_permissions=True)
