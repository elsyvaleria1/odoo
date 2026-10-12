import logging
import time
from typing import TYPE_CHECKING, Any

from odoo.libs.debug_log import DebugLog
from odoo.tools.security import consteq

if TYPE_CHECKING:
    from odoo.api import Environment
    from odoo.db import BaseCursor
    from odoo.http import Request, Session
else:
    Session = Any
    Environment = Any
    Request = Any
    BaseCursor = Any

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)


def get_session_token(session: Session, env: Environment) -> str | None:
    user = env["res.users"].browse(session.uid)
    with _debug.perf("session.token_computed", cr=env.cr, uid=session.uid):
        return user._get_session_token(session.sid)


def is_session_valid(
    session: Session,
    env: Environment,
    request: Request | None = None,
    *,
    fresh_primary_cr: BaseCursor | None = None,
    binding_valid: bool | None = None,
) -> bool:
    session._remove_old_sessions()
    if "deletion_time" in session and session["deletion_time"] <= time.time():
        _debug.logic("session.invalid", reason="deleted", uid=session.uid)
        return False
    expected = get_session_token(session, env)
    actual = session.session_token
    if not isinstance(expected, str) or not expected:
        _debug.logic("session.invalid", reason="no_expected_token", uid=session.uid)
        return False
    if not isinstance(actual, str) or not consteq(expected, actual):
        _debug.logic("session.invalid", reason="token_mismatch", uid=session.uid)
        return False
    if binding_valid is None:
        binding_valid = env["auth.user.client"]._is_session_valid(
            session, fresh_primary_cr=fresh_primary_cr
        )
    if not binding_valid:
        return False
    if request:
        try:
            with _debug.perf("session.device_log_updated", cr=env.cr, uid=session.uid):
                env["auth.user.client"]._observe(request)
        except Exception:
            _logger.warning(
                "Device-log update failed for a valid session; keeping the "
                "session authenticated",
                exc_info=True,
            )
            _debug.logic("session.device_log_failed", uid=session.uid)
    _debug.logic("session.valid", uid=session.uid, device_logged=bool(request))
    return True
