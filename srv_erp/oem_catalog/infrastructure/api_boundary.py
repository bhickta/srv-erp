"""Authentication and transaction semantics shared by the public OEM API."""
import time
from functools import wraps

import frappe
from frappe import _

from ..domain.models import CatalogError


def endpoint(write=False):
    def decorate(fn):
        @wraps(fn)
        def call(*args, **kwargs):
            if frappe.session.user == 'Guest':
                frappe.throw(_('Sign in to use OEM Catalog.'), frappe.PermissionError)
            for attempt in range(3):
                if write: frappe.db.savepoint('oem_command_boundary')
                try:
                    result = fn(*args, **kwargs)
                    if isinstance(result, dict): result.setdefault('api_version', 1)
                    return result
                except (frappe.QueryDeadlockError, frappe.QueryTimeoutError):
                    # InnoDB deadlocks invalidate every savepoint. Retry the
                    # entire actor-scoped command in a fresh transaction.
                    frappe.db.rollback()
                    if not write or attempt == 2: raise
                    time.sleep(.05 * (attempt + 1))
                except CatalogError as error:
                    if write: frappe.db.rollback(save_point='oem_command_boundary')
                    frappe.throw(_(error.code + ': ' + str(error)))
                except Exception:
                    if write: frappe.db.rollback(save_point='oem_command_boundary')
                    raise
        return frappe.whitelist(methods=['POST'] if write else ['GET', 'POST'])(call)
    return decorate
