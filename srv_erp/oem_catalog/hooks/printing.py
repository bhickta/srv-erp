import frappe
from frappe import _


def before_print(doc, method=None, *args, **kwargs):
    if not doc.get('oem_unresolved_line_count'): return
    format_name = frappe.form_dict.get('format')
    if format_name and format_name != 'Standard':
        frappe.throw(_('Use Standard draft print for an incomplete OEM order. Its heading identifies pending approval and incomplete estimates.'))
    doc.select_print_heading = None
    doc.print_heading = _('Pending Item Approval — Estimated / Incomplete')


def guard_official_print(doc):
    if doc.get('oem_unresolved_line_count'):
        frappe.throw(_('An incomplete OEM order cannot use the official order-slip print. Use Standard draft print with the pending approval heading.'))
