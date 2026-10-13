import logging

from odoo import SUPERUSER_ID, models
from odoo.http import request
from odoo.service import api_scope
from odoo.tools import SQL

from .. import unix_peer

_logger = logging.getLogger(__name__)

DEFAULT_KEYS_PATH = "/etc/ssh/authorized_keys/%u"


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @classmethod
    def _auth_method_bearer(cls, scope: str = api_scope.RPC_SCOPE) -> None:
        # An Authorization header or a browser session keeps the standard path; only
        # a bare call from this host is identified by its Unix user.
        if request.httprequest.headers.get("Authorization") or request.env.uid:
            return super()._auth_method_bearer(scope)
        uid = cls._unix_peer_uid()
        if not uid:
            return super()._auth_method_bearer(scope)
        request.update_env(user=uid)
        request.update_context(**request.env.user.context_get())
        request.session.can_save = False
        cls._enter_api_scope(scope, uid)
        cls._auth_method_user()
        return None

    @classmethod
    def _unix_peer_uid(cls) -> int | None:
        """Return the Odoo user named by the Unix user on the other end of the request.

        :return: the user id, or None when the request is not a loopback call from
            a member of ``auth_unix_peer.group`` whose keys name one internal user
        :rtype: int | None
        """
        settings = request.env.registry.settings
        group = settings.get(request.env, "auth_unix_peer.group", False)
        if not group:
            return None
        environ = request.httprequest.environ
        # The socket's own addresses, not the ones a proxy header rewrote.
        original = environ.get("werkzeug.proxy_fix.orig") or {}
        address = original.get("REMOTE_ADDR", environ.get("REMOTE_ADDR"))
        port = environ.get("REMOTE_PORT")
        server_port = original.get("SERVER_PORT", environ.get("SERVER_PORT"))
        if not (address and port and server_port) or not unix_peer.is_loopback(address):
            return None
        try:
            owner = unix_peer.tcp_owner_uid(
                address, int(port), address, int(server_port)
            )
        except OSError, ValueError:
            _logger.warning(
                "unix peer: cannot ask the kernel who owns %s:%s", address, port
            )
            return None
        name = owner is not None and unix_peer.member_name(owner, group)
        if not name:
            return None
        path = settings.get(request.env, "auth_unix_peer.keys_path", DEFAULT_KEYS_PATH)
        login = unix_peer.login_from_keys(path.replace("%u", name))
        if not login:
            _logger.warning("unix peer: the keys of %s name no single login", name)
            return None
        # Nobody is authenticated yet, so read the table itself, as res.users.apikeys
        # does to match a key. share is stored: false means an internal user.
        request.env.cr.execute(
            SQL(
                "SELECT id FROM res_users WHERE login = %s AND active AND NOT share",
                login,
            )
        )
        row = request.env.cr.fetchone()
        if not row or row[0] == SUPERUSER_ID:
            _logger.warning(
                "unix peer: %s names %r, which is not an active internal user",
                name,
                login,
            )
            return None
        _logger.info("unix peer: %s acts as %s (uid %s)", name, login, row[0])
        return row[0]
