"""Seed only synthetic legacy masters for migration fingerprint comparison."""
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
    from erpnext.setup.setup_wizard.setup_wizard import setup_complete
    if not frappe.db.exists('Company', 'OEM Baseline Company'):
        setup_complete(frappe._dict({'currency': 'INR', 'full_name': 'Synthetic Baseline Operator', 'company_name': 'OEM Baseline Company',
            'company_abbr': 'OB', 'country': 'India', 'timezone': 'Etc/UTC', 'language': 'english', 'chart_of_accounts': 'Standard',
            'email': 'baseline@example.com', 'password': 'synthetic-baseline-only', 'fy_start_date': '2026-01-01', 'fy_end_date': '2026-12-31'}))
    if not frappe.db.exists('Customer', 'OEM Baseline Customer'):
        frappe.get_doc({'doctype': 'Customer', 'customer_name': 'OEM Baseline Customer', 'customer_type': 'Company', 'customer_group': 'Commercial', 'territory': 'India'}).insert()
    if not frappe.db.exists('Brand', 'OEM Baseline Brand'):
        frappe.get_doc({'doctype': 'Brand', 'brand': 'OEM Baseline Brand'}).insert()
    if not frappe.db.exists('Item', 'OEM-BASELINE-LEGACY'):
        item = frappe.get_doc({'doctype': 'Item', 'item_code': 'OEM-BASELINE-LEGACY', 'item_name': 'Synthetic legacy enclosure',
            'item_group': 'Products', 'stock_uom': 'Nos', 'is_stock_item': 1, 'brand': 'OEM Baseline Brand',
            'uoms': [{'uom': 'Nos', 'conversion_factor': 1}, {'uom': 'Box', 'conversion_factor': 12}]}).insert()
        frappe.get_doc({'doctype': 'Item Price', 'item_code': item.name, 'price_list': 'Standard Selling', 'price_list_rate': 10, 'currency': 'INR', 'uom': 'Nos'}).insert()
        from srv_erp.package_barcode.service import PackageBarcodeGenerator
        PackageBarcodeGenerator(item.name, 'Box', 3).generate()
    frappe.db.commit()
    print('Synthetic legacy Customer, Brand, Item, price, UOMs and barcode batch prepared')
finally: frappe.destroy()
