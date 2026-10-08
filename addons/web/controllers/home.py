import hashlib
import logging
from typing import Any

from odoo import SUPERUSER_ID, http
from odoo.exceptions import AccessDenied, AccessError
from odoo.http import Response, request
from odoo.libs.debug_log import DebugLog
from odoo.libs.json import dumps as json_dumps
from odoo.tools import config
from odoo.tools.json import json_default
from odoo.tools.misc import hmac, register_signed_scope
from odoo.tools.translate import LazyTranslate

from .utils import (
    _get_login_redirect_url,
    _is_local_url,
    is_user_internal,
    select_db,
)

_lt = LazyTranslate(__name__)
_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)

BROWSER_CACHE_SCOPE = register_signed_scope(
    "browser_cache_key",
    purpose="the key the web client encrypts its browser cache with, bound to "
    "the session's user and credentials",
    lifetime="undated: it changes with the session token values",
)


SIGN_UP_REQUEST_PARAMS = {
    "db",
    "login",
    "debug",
    "token",
    "message",
    "error",
    "scope",
    "mode",
    "redirect",
    "redirect_hostname",
    "email",
    "name",
    "partner_id",
    "password",
    "confirm_password",
    "city",
    "country_id",
    "lang",
    "signup_email",
}
LOGIN_SUCCESSFUL_PARAMS: set[str] = set()
CREDENTIAL_PARAMS = {"login", "password", "type"}


class Home(http.Controller):
    @http.route("/", type="http", auth="none")
    def index(self, **kw: Any) -> Response:
        _debug.lifecycle("index")
        if (
            request.db
            and request.session.uid
            and not is_user_internal(request.session.uid)
        ):
            _debug.logic("index_external_user", redirect="/web/login_successful")
            return request.redirect_query("/web/login_successful", query=request.params)
        return request.redirect_query("/odoo", query=request.params)

    def _web_client_readonly(self, rule: Any, args: Any) -> bool:
        return False

    @http.route(
        ["/web", "/odoo", "/odoo/<path:subpath>", "/scoped_app/<path:subpath>"],
        type="http",
        auth="none",
        readonly=_web_client_readonly,
    )
    def web_client(self, s_action: str | None = None, **kw: Any) -> Response:
        if _debug.lifecycle.enabled:
            _debug.lifecycle("web_client", kw=sorted(kw))
        select_db()
        if not request.session.uid:
            _debug.pipeline("web_client_anonymous", redirect="/web/login", status=303)
            return request.redirect_query(
                "/web/login",
                query={"redirect": request.httprequest.full_path},
                code=303,
            )
        if kw.get("redirect") and _is_local_url(kw["redirect"]):
            _debug.pipeline("web_client_local_redirect", redirect=kw["redirect"])
            return request.redirect(kw["redirect"], 303)
        if not is_user_internal(request.session.uid):
            _debug.pipeline(
                "web_client_external_user", uid=request.session.uid, status=303
            )
            return request.redirect("/web/login_successful", 303)

        request.update_env(user=request.session.uid)
        try:
            with _debug.perf("web_client_bootstrap_hook", cr=request.env.cr):
                request.env.user._on_webclient_bootstrap()
            with _debug.perf("web_client_rendering_context", cr=request.env.cr):
                context = request.env["ir.http"].webclient_rendering_context()

            hmac_payload = request.env.user._get_session_token_values()
            session_info = context["session_info"]
            session_info["browser_cache_secret"] = hmac(
                request.env(su=True), BROWSER_CACHE_SCOPE, hmac_payload
            )
            if _debug.pipeline.enabled:
                _debug.pipeline(
                    "web_client_render",
                    uid=request.session.uid,
                    context=sorted(context),
                    session_info=len(session_info),
                )

            with _debug.perf("web_client_bootstrap_render", cr=request.env.cr):
                response = request.render("web.webclient_bootstrap", qcontext=context)
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Cache-Control"] = "no-store"
            response.set_cookie(
                "content_density", request.env["ir.http"].content_density()
            )
            response.set_cookie("color_scheme", request.env["ir.http"].color_scheme())
            return response
        except AccessError:
            _debug.logic("web_client_bootstrap_access_error")
            return request.redirect("/web/login?error=access")

    @http.route(
        "/web/webclient/load_menus",
        type="http",
        auth="user",
        methods=["GET"],
        readonly=True,
    )
    def web_load_menus(
        self, lang: str | None = None, hash: str | None = None
    ) -> Response:
        _debug.lifecycle(
            "menus_load",
            lang=lang,
            client_hash=(hash or "")[:12] or None,
            debug=request.session.debug,
        )
        if lang:
            request.update_context(lang=lang)

        with _debug.perf("menus_load_web_menus", cr=request.env.cr):
            menus = request.env["ir.ui.menu"].load_web_menus(request.session.debug)
        with _debug.perf("menus_dumps_hash"):
            body = json_dumps(menus, default=json_default)
            current_hash = hashlib.sha256(body.encode()).hexdigest()
        headers = [
            ("Cache-Control", "no-store"),
            ("X-Menus-Hash", current_hash),
        ]
        if hash and hash == current_hash:
            _debug.logic("menus_hash_match_not_modified", body_built=True)
            return request.prepare_response("", headers, status=304)
        _debug.perf.count(
            "menus_size", menus=len(menus), bytes=len(body), hash=current_hash[:12]
        )
        headers.append(("Content-Type", "application/json; charset=utf-8"))
        return request.prepare_response(body, headers)

    def _login_redirect(self, uid: int, redirect: str | None = None) -> str:
        return _get_login_redirect_url(uid, redirect)

    @http.route(
        "/web/login",
        type="http",
        auth="none",
        readonly=False,
        list_as_website_content=_lt("Login"),
    )
    def web_login(self, redirect: str | None = None, **kw: Any) -> Response:
        if _debug.lifecycle.enabled:
            _debug.lifecycle(
                "web_login", redirect=redirect, params=sorted(request.params)
            )
        select_db()
        request.params["login_success"] = False
        if request.httprequest.method == "GET" and redirect and request.session.uid:
            if not _is_local_url(redirect):
                _debug.logic("login_redirect_not_local", redirect=redirect, to="/odoo")
                redirect = "/odoo"
            _debug.pipeline(
                "login_already_authenticated",
                uid=request.session.uid,
                redirect=redirect,
            )
            return request.redirect(redirect)

        if request.env.uid is None:
            if request.session.uid is None:
                _debug.logic("login_env_unbound", session="anonymous", bind="public")
                request.env["ir.http"]._auth_method_public()
            else:
                _debug.logic(
                    "login_env_unbound", session=request.session.uid, bind="session_uid"
                )
                request.update_env(user=request.session.uid)

        values = {
            k: v for k, v in request.params.items() if k in SIGN_UP_REQUEST_PARAMS
        }
        try:
            values["databases"] = request.app.get_dbs_listed()
        except AccessDenied:
            _debug.logic("login_db_list_denied")
            values["databases"] = None

        if request.httprequest.method == "POST":
            try:
                credential = {
                    key: value
                    for key, value in request.params.items()
                    if key in CREDENTIAL_PARAMS and value
                }
                credential.setdefault("type", "password")
                _debug.pipeline(
                    "login_post",
                    login=credential.get("login"),
                    credential_type=credential["type"],
                    has_password=bool(credential.get("password")),
                )
                if request.env["res.users"]._is_captcha_login_required(credential):
                    _debug.logic("login_captcha_required")
                    request.env["ir.http"]._check_request_captcha_token("login")
                with _debug.perf("login_authenticate", cr=request.env.cr):
                    auth_info = request.session.authenticate(request.env, credential)
                request.params["login_success"] = True
                _debug.pipeline(
                    "login_success",
                    uid=auth_info["uid"],
                    session_uid=request.session.uid,
                )
                return request.redirect(
                    self._login_redirect(auth_info["uid"], redirect=redirect)
                )
            except AccessDenied as e:
                if e.args == AccessDenied().args:
                    _debug.logic("login_denied", reason="wrong_credentials")
                    values["error"] = request.env._("Wrong login/password")
                else:
                    _debug.logic("login_denied", reason=e.args[0])
                    values["error"] = e.args[0]
        elif request.params.get("error") == "access":
            _debug.logic("login_access_error_shown")
            values["error"] = request.env._(
                "Only employees can access this database. Please contact the administrator."
            )

        if "login" not in values and request.session.get("auth_login"):
            _debug.logic("login_prefilled_from_session")
            values["login"] = request.session.get("auth_login")

        if not config["list_db"]:
            values["disable_database_manager"] = True

        with _debug.perf("login_render", cr=request.env.cr):
            response = request.render("web.login", values)
        response.headers["Cache-Control"] = "no-cache"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Content-Security-Policy"] = "frame-ancestors 'self'"
        return response

    @http.route(
        "/web/login_successful",
        type="http",
        auth="user",
        website=True,
        sitemap=False,
        readonly=True,
    )
    def login_successful_external_user(self, **kwargs: Any) -> Response:
        valid_values = {k: v for k, v in kwargs.items() if k in LOGIN_SUCCESSFUL_PARAMS}
        if _debug.lifecycle.enabled:
            _debug.lifecycle(
                "login_successful", kept=sorted(valid_values), received=len(kwargs)
            )
        return request.render("web.login_successful", valid_values)

    @http.route("/web/become", type="http", auth="user", sitemap=False, readonly=False)
    def switch_to_admin(self) -> Response:
        uid = request.env.user.id
        _debug.lifecycle("become", uid=uid)
        if request.env.user._is_system():
            session = request.session
            retired = session._retired_identifier()
            session["pre_login"] = session.login
            session["pre_uid"] = uid = SUPERUSER_ID
            session.finalize_login(request.env)
            if retired:
                request.env["auth.user.client.session"]._mark_logged_out(retired)
            _debug.pipeline("become_superuser", retired=retired and retired[:8])
        else:
            _debug.logic("become_refused_not_system", uid=uid)

        return request.redirect(self._login_redirect(uid))

    @http.route(["/robots.txt"], type="http", auth="none")
    def robots(self, **kwargs: Any) -> Response:
        allowed_routes = self._get_allowed_robots_routes()
        _debug.lifecycle("robots", allowed=len(allowed_routes))
        robots_content = ["User-agent: *", "Disallow: /"]
        robots_content.extend(f"Allow: {route}" for route in allowed_routes)

        return request.prepare_response(
            "\n".join(robots_content), [("Content-Type", "text/plain; charset=utf-8")]
        )

    def _get_allowed_robots_routes(self) -> list[str]:
        return []
