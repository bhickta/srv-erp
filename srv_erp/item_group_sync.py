import frappe
from frappe import _


def validate_item_group_sync(doc, method=None):
	if not doc.variant_of:
		return

	template_item_group = frappe.db.get_value("Item", doc.variant_of, "item_group")
	if not template_item_group:
		return

	if doc.item_group == template_item_group:
		return

	if doc.has_value_changed("item_group"):
		frappe.throw(
			_(
				"Item Group for variant {0} is controlled by template {1}. Change Item Group on the template instead."
			).format(frappe.bold(doc.name), frappe.bold(doc.variant_of))
		)

	doc.item_group = template_item_group


def sync_template_item_group_to_variants(doc, method=None):
	if doc.variant_of or not doc.has_variants or not doc.item_group:
		return

	if not has_item_group_changed(doc):
		return

	sync_variant_item_groups(doc.name, doc.item_group)


def sync_variant_item_groups(template_item, item_group):
	frappe.db.sql(
		"""
		update `tabItem`
		set item_group = %(item_group)s,
			modified = now(),
			modified_by = %(user)s
		where variant_of = %(template_item)s
			and ifnull(item_group, '') != %(item_group)s
		""",
		{
			"template_item": template_item,
			"item_group": item_group,
			"user": frappe.session.user,
		},
	)


def sync_all_variant_item_groups() -> int:
	updated = frappe.db.sql(
		"""
		update `tabItem` variant
		inner join `tabItem` template on template.name = variant.variant_of
		set variant.item_group = template.item_group,
			variant.modified = now(),
			variant.modified_by = %(user)s
		where ifnull(variant.variant_of, '') != ''
			and ifnull(template.item_group, '') != ''
			and ifnull(variant.item_group, '') != template.item_group
		""",
		{"user": frappe.session.user},
	)
	return updated or 0


def has_item_group_changed(doc) -> bool:
	if doc.is_new():
		return True

	previous = doc.get_doc_before_save()
	if not previous:
		return False

	return previous.item_group != doc.item_group
