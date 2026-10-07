"""Synthetic prerequisites for the guarded OEM Bench only."""
from pathlib import Path

import frappe


def prepare():
    root = Path(frappe.get_site_path()).resolve()
    if root != Path('/home/bhickta/development/oem-bench/sites/oem-test.localhost'):
        raise RuntimeError('Synthetic OEM setup requires the declared isolated site')
    for email in ('oem-manager-one@example.com', 'oem-manager-two@example.com'):
        if not frappe.db.exists('User', email):
            frappe.get_doc({'doctype': 'User', 'email': email, 'first_name': 'Synthetic Manager', 'send_welcome_email': 0,
                            'roles': [{'role': 'System Manager'}]}).insert(ignore_permissions=True)
    if not frappe.db.exists('Item Attribute', 'Brand'):
        frappe.flags.syncing_brand_attribute_values = True
        try:
            frappe.get_doc({'doctype': 'Item Attribute', 'attribute_name': 'Brand'}).insert(ignore_permissions=True)
        finally:
            frappe.flags.syncing_brand_attribute_values = False


def complete_setup():
    prepare()
    from erpnext.setup.setup_wizard.setup_wizard import setup_complete
    if not frappe.db.exists('Company', 'OEM Example Company'):
        setup_complete(frappe._dict({'currency': 'INR', 'full_name': 'Synthetic Operator', 'company_name': 'OEM Example Company',
                        'company_abbr': 'OEM', 'timezone': 'Etc/UTC', 'industry': 'Manufacturing', 'country': 'India',
                        'language': 'english', 'email': 'oem-setup@example.com', 'password': 'synthetic-tests-only',
                        'chart_of_accounts': 'Standard', 'fy_start_date': '2026-01-01', 'fy_end_date': '2026-12-31'}))
    return {'synthetic_setup': True}
