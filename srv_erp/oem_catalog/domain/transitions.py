from .models import CatalogError


def decide(status, target, requester, actor, reason, allow_self=False):
    if status != 'Pending' or target not in ('Approved', 'Rejected', 'Cancelled'):
        raise CatalogError('REQUEST_STATE_CONFLICT', 'Request is no longer pending')
    if target == 'Approved' and requester == actor and not allow_self:
        raise CatalogError('FORBIDDEN', 'A different approver must release this request')
    if target in ('Rejected', 'Cancelled') and not (reason or '').strip():
        raise CatalogError('INVALID_INPUT', 'A reason is required')
    return target
