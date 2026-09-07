import frappe
from frappe.utils.nestedset import get_descendants_of


@frappe.whitelist()
@frappe.read_only()
def get_customers_in_group(customer_group):
	"""Return customers using their current Customer Group tree membership."""
	return _get_customers_in_group(customer_group)


def _get_customers_in_group(customer_group):
	if not customer_group or not frappe.db.exists("Customer Group", customer_group):
		return []

	groups = [customer_group, *get_descendants_of("Customer Group", customer_group)]
	return frappe.get_list(
		"Customer",
		filters={"customer_group": ("in", groups)},
		pluck="name",
		limit_page_length=0,
	)
