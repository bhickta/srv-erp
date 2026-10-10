from pathlib import Path
import os
import sys

from guard import inspect

bench = inspect(Path('/home/bhickta/development/oem-bench'), 'oem-dev.localhost')
sys.path.insert(0, '/home/bhickta/development/srv-erp-oem-baseline')
os.chdir(bench / 'sites')
import frappe
frappe.init(site='oem-dev.localhost'); frappe.connect(); frappe.set_user('Administrator')
try:
    for role in ('Masters Item Requester', 'Masters Item Approver'):
        if not frappe.db.exists('Role', role): frappe.get_doc({'doctype': 'Role', 'role_name': role}).insert(ignore_permissions=True)
    for email in ('baseline-manager-one@example.com', 'baseline-manager-two@example.com'):
        if not frappe.db.exists('User', email): frappe.get_doc({'doctype': 'User', 'email': email, 'first_name': 'Synthetic Baseline Manager', 'send_welcome_email': 0, 'roles': [{'role': 'System Manager'}]}).insert(ignore_permissions=True)
    if not frappe.db.exists('Item Attribute', 'Brand'):
        frappe.get_doc({'doctype': 'Item Attribute', 'attribute_name': 'Brand'}).insert(ignore_permissions=True)
    frappe.db.commit()
finally: frappe.destroy()
