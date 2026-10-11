from collections.abc import Callable

from odoo.http import request
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


def consume_request_allowance(
    key: tuple, consume: Callable[[], bool], *, cr=None
) -> bool:
    if not request:
        return consume()
    allowances = getattr(request.scratch, "inbound_allowances", None)
    if allowances is None:
        allowances = request.scratch.inbound_allowances = set()
    if key in allowances:
        _debug.logic("inbound_allowance_reused", kind=key[0])
        return True
    if not consume():
        return False
    if cr is None:
        allowances.add(key)
    else:
        cr.postcommit.add(lambda: allowances.add(key))
    return True
