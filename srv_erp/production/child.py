import frappe
from frappe.model.document import Document


class ProductionChild(Document):
	"""Resolve the actual parent for standalone child-document permission checks.

	Frappe v15's child permission helper uses parent_doc when the property exists.
	An independently loaded row otherwise supplies None and falls back to parent
	DocType access, skipping the parent's document-level ownership restriction.
	"""

	@property
	def parent_doc(self):
		parent = super().parent_doc
		if parent is not None:
			return parent
		if self.get("parent"):
			if self.parenttype != self.production_parent_doctype:
				frappe.throw(frappe._("Invalid production item parent."), frappe.PermissionError)
			return frappe.get_doc(self.parenttype, self.parent)
		return None

	@parent_doc.setter
	def parent_doc(self, value):
		Document.parent_doc.fset(self, value)
