from contextlib import ExitStack
from typing import Any
from urllib.parse import urlencode

from odoo import api, http
from odoo.exceptions import AccessError
from odoo.http import Response, request
from odoo.libs.debug_log import DebugLog
from odoo.libs.json import dumps as json_dumps
from odoo.modules.registry import Registry

from .utils import _is_local_url

_debug = DebugLog(__name__)


class Session(http.Controller):
    @http.route(
        "/web/session/get_session_info",
        type="jsonrpc",
        auth="user",
        readonly=True,
    )
    def get_session_info(self) -> dict[str, Any]:
        _debug.lifecycle("get_session_info", marks_dirty=True)
        request.session.mark_dirty()
        with _debug.perf("session_info", cr=request.env.cr):
            return request.env["ir.http"].session_info()

    @http.route(
        "/web/session/authenticate", type="jsonrpc", auth="none", readonly=False
    )
    def authenticate(
        self,
        db: str,
        login: str,
        password: str,
        base_location: str | None = None,
    ) -> dict[str, Any]:
        _debug.lifecycle(
            "authenticate", db=db, login=login, has_password=bool(password)
        )
        if not request.app.filter_dbs_served([db]):
            _debug.logic("authenticate_db_not_served", db=db)
            msg = "Database not found."
            raise AccessError(msg)

        with ExitStack() as stack:
            if request.db != db:
                _debug.logic("authenticate_own_cursor", request_db=request.db, db=db)
                cr = stack.enter_context(Registry(db).cursor())
                env = api.Environment(cr, None, {})
            else:
                env = request.env

            credential = {
                "login": login,
                "password": password,
                "type": "password",
            }
            with _debug.perf("authenticate", cr=env.cr, login=login):
                auth_info = request.session.authenticate(env, credential)
            if auth_info["uid"] != request.session.uid:
                _debug.logic(
                    "authenticate_uid_mismatch",
                    uid=auth_info["uid"],
                    session_uid=request.session.uid,
                    mfa_pending_suspected=True,
                )
                return {"uid": None}

            request.session.db = db
            request._save_session(env)
            _debug.pipeline(
                "authenticate_to_session_info", uid=request.session.uid, db=db
            )

            with _debug.perf(
                "authenticate_session_info", cr=env.cr, uid=request.session.uid
            ):
                return env["ir.http"].with_user(request.session.uid).session_info()

    @http.route("/web/session/modules", type="jsonrpc", auth="user", readonly=True)
    def modules(self) -> list[str]:
        loaded = list(request.env.registry.loaded_modules)
        _debug.lifecycle("modules", loaded=len(loaded))
        return loaded

    @http.route("/web/session/check", type="jsonrpc", auth="user", readonly=True)
    def check(self) -> None:
        _debug.lifecycle("check")

    @http.route("/web/session/account", type="jsonrpc", auth="user", readonly=True)
    def account(self) -> str:
        _debug.lifecycle("account")
        ICP = request.env["ir.config_parameter"].sudo()
        params = {
            "response_type": "token",
            "client_id": ICP.get_param("database.uuid") or "",
            "state": json_dumps({"d": request.db, "u": ICP.get_param("web.base.url")}),
            "scope": "userinfo",
        }
        return "https://accounts.odoo.com/oauth2/auth?" + urlencode(params)

    @http.route("/web/session/destroy", type="jsonrpc", auth="user", readonly=False)
    def destroy(self) -> None:
        _debug.lifecycle("destroy")
        request.session.logout()

    @http.route("/web/session/logout", type="http", auth="none", readonly=False)
    def logout(self, redirect: str = "/odoo") -> Response:
        _debug.lifecycle("logout", redirect=redirect)
        request.session.logout(keep_db=True)
        if not _is_local_url(redirect):
            _debug.logic("logout_redirect_not_local", redirect=redirect, to="/odoo")
            redirect = "/odoo"
        return request.redirect(redirect, 303)
