import frappe


def get_dynamic_variant_profile_name(template_item: str) -> str | None:
	"""Return a profile by its unique template link, which survives Item renames."""
	return frappe.db.get_value(
		"Dynamic Variant Profile",
		{"item_template": template_item},
		"name",
	)
