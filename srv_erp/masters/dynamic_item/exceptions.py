import frappe


class DynamicItemConflict(frappe.ValidationError):
	"""Raised when a request conflicts with existing Item master state."""
