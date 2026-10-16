import hashlib
from pathlib import Path

import frappe
from frappe import _
from frappe.utils import getdate, now_datetime, today

from srv_erp.oem_catalog.infrastructure.commands import Receipt, audit, lock, save
from srv_erp.oem_catalog.infrastructure.documents import internal_command
from srv_erp.oem_catalog.permissions import readable, require_role


def verified_bytes(revision, context=None):
    file = readable('File', revision.private_file)
    if not file.is_private or file.file_url.startswith(('http:', 'https:')):
        frappe.throw(_('Assets must use private local files.'))
    path = Path(file.get_full_path()).resolve()
    private_root = Path(frappe.get_site_path('private', 'files')).resolve()
    if not path.is_relative_to(private_root) or not path.is_file():
        frappe.throw(_('Invalid asset file ownership.'))
    if path.stat().st_size > 20 * 1024 * 1024:
        frappe.throw(_('Asset exceeds the supported size.'))
    content = path.read_bytes()
    checksum = hashlib.sha256(content).hexdigest()
    if revision.content_sha256 and checksum != revision.content_sha256:
        frappe.throw(_('ITEM_DRIFT: approved asset bytes changed.'))
    if context is not None:
        asset = readable('OEM Asset', revision.asset)
        effective = getdate(context.get('effective_date') or today())
        if revision.state != 'Approved' or (asset.permitted_brand and asset.permitted_brand != context.get('brand')) or (revision.valid_from and effective < getdate(revision.valid_from)) or (revision.valid_until and effective > getdate(revision.valid_until)):
            frappe.throw(_('Asset is unavailable in this context.'), frappe.PermissionError)
    return checksum


def approve_asset(name, expected_modified, idempotency_key):
    require_role('manager')
    revision = readable('OEM Asset Revision', name, 'write')
    receipt = Receipt('approve_asset', idempotency_key, {'name': name, 'modified': expected_modified})
    if receipt.replay:
        return receipt.replay
    revision = lock('OEM Asset Revision', name)
    if str(revision.modified) != expected_modified or revision.state != 'Draft':
        frappe.throw(_('STALE_CONFIGURATION: refresh this asset revision.'))
    revision.content_sha256 = verified_bytes(revision)
    revision.state, revision.approved_by, revision.approved_on = 'Approved', frappe.session.user, now_datetime()
    save(revision)
    audit('approve_asset', revision, receipt.key)
    return receipt.finish({'asset_revision': revision.name, 'checksum': revision.content_sha256})


def protect_file(doc, method=None):
    if doc.is_new() or not frappe.db.exists('DocType', 'OEM Asset Revision'):
        return
    referenced = frappe.db.exists('OEM Asset Revision', {'private_file': doc.name, 'state': ['in', ['Approved', 'Retired']]})
    if not referenced:
        return
    if method == 'on_trash':
        frappe.throw(_('An approved OEM asset file cannot be deleted.'))
    old = doc.get_doc_before_save()
    if old and any(doc.get(key) != old.get(key) for key in ('file_url', 'is_private', 'content_hash', 'attached_to_doctype', 'attached_to_name')):
        frappe.throw(_('An approved OEM asset file cannot be replaced or reattached.'))
