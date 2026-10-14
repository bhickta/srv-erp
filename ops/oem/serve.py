"""Loopback-only synthetic OEM browser test server (no debugger)."""
import os
from pathlib import Path

from guard import inspect

bench = inspect(Path('/home/bhickta/development/oem-bench'), 'oem-test.localhost')
os.chdir(bench / 'sites')
import frappe.app
from werkzeug.serving import run_simple

frappe.app._site = 'oem-test.localhost'
frappe.app._sites_path = '.'
run_simple('127.0.0.1', 8011, frappe.app.application_with_statics(), use_reloader=False, use_debugger=False, threaded=True)
