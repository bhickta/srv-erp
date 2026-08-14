from contextlib import contextmanager

import frappe


@contextmanager
def dynamic_item_service_context():
	"""Mark trusted writes performed by the dynamic Item domain services."""
	previous = getattr(frappe.flags, "dynamic_item_service", False)
	frappe.flags.dynamic_item_service = True
	try:
		yield
	finally:
		frappe.flags.dynamic_item_service = previous
