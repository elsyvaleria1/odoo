import logging
from urllib.parse import quote_plus, unquote_plus, urlencode, urlsplit

from werkzeug.exceptions import BadRequest, NotFound

from odoo import SUPERUSER_ID, api, http
from odoo.exceptions import AccessDenied
from odoo.http import fragment_to_query_string, request
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.modules.registry import Registry
from odoo.tools import consume_session_state, issue_session_state, register_signed_scope
from odoo.tools.misc import clean_context

from odoo.addons.auth_signup.controllers.main import AuthSignupHome as Home
from odoo.addons.web.controllers.utils import _get_login_redirect_url, select_db

_logger = logging.getLogger(__name__)

_LOGIN_STATE_MAX_AGE_SECONDS = 600

LOGIN_STATE_SCOPE = register_signed_scope(
    "auth_oauth.login_state",
    purpose="the state a sign-in carries through the OAuth provider back to "
    "/auth_oauth/signin: the provider, the page to land on and the signup "
    "token, bound to the database and the browser session that started it",
    lifetime=f"its expiry: the sign-in refuses a state older than "
    f"{_LOGIN_STATE_MAX_AGE_SECONDS} seconds, or one already consumed",
)


# ----------------------------------------------------------
# Controller
# ----------------------------------------------------------
class OAuthLogin(Home):
    def list_providers(self):
        try:
            providers = (
                request.env["auth.oauth.provider"]
                .sudo()
                .search_read([("enabled", "=", True)])
            )
        except KeyError:
            providers = []
        params = {
            key: request.params[key]
            for key in ("redirect", "token")
            if request.params.get(key)
        }
        for provider in providers:
            provider["auth_link"] = f"/auth_oauth/authorize/{provider['id']}"
            if params:
                provider["auth_link"] += f"?{urlencode(params)}"
        return providers

    @http.route(
        "/auth_oauth/authorize/<int:provider_id>",
        type="http",
        auth="none",
        readonly=False,
    )
    def authorize(self, provider_id, redirect=None, token=None, **kw):
        select_db()
        provider = (
            request.env["auth.oauth.provider"].sudo().browse(provider_id).exists()
        )
        if not provider.enabled:
            raise NotFound
        url_root = request.httprequest.url_root
        claims = {"p": provider.id}
        if redirect:
            if not redirect.startswith(("/", "http://", "https://")):
                redirect = f"/{redirect}"
            claims["r"] = quote_plus(redirect)
        if token:
            claims["t"] = token
        signed = issue_session_state(
            request.env,
            LOGIN_STATE_SCOPE,
            request.session,
            claims,
            max_age_seconds=_LOGIN_STATE_MAX_AGE_SECONDS,
        )
        params = {
            "response_type": "token",
            "client_id": provider.client_id,
            "redirect_uri": url_root + "auth_oauth/signin",
            "scope": provider.scope,
            "state": json_dumps({"d": request.session.db, "token": signed}),
        }
        return request.redirect(
            f"{provider.auth_endpoint}?{urlencode(params)}", 303, local=False
        )

    @http.route()
    def web_login(self, *args, **kw):
        select_db()
        if (
            request.httprequest.method == "GET"
            and request.session.uid
            and request.params.get("redirect")
        ):
            # Redirect if already logged in and redirect param is present
            return request.redirect(request.params.get("redirect"))
        providers = self.list_providers()

        response = super().web_login(*args, **kw)
        if response.is_qweb:
            error = request.params.get("oauth_error")
            if error == "1":
                error = request.env._("Sign up is not allowed on this database.")
            elif error == "2":
                error = request.env._("Access Denied")
            elif error == "3":
                error = request.env._(
                    "You do not have access to this database or your invitation has expired. Please ask for an invitation and be sure to follow the link in your invitation email."
                )
            else:
                error = None

            response.qcontext["providers"] = providers
            if error:
                response.qcontext["error"] = error

        return response

    def get_auth_signup_qcontext(self):
        result = super().get_auth_signup_qcontext()
        result["providers"] = self.list_providers()
        return result


class OAuthController(http.Controller):
    @http.route("/auth_oauth/signin", type="http", auth="none", readonly=False)
    @fragment_to_query_string
    def signin(self, **kw):
        try:
            state = json_loads(kw["state"])
            dbname = state["d"]
        except KeyError, TypeError, ValueError:
            raise BadRequest from None
        if not isinstance(dbname, str) or not request.app.filter_dbs_served([dbname]):
            raise BadRequest
        select_db(db=dbname)
        claims = consume_session_state(
            request.env, LOGIN_STATE_SCOPE, request.session, state.get("token")
        )
        if claims is None:
            _logger.warning(
                "OAuth2: refused a sign-in whose state this session did not start"
            )
            redirect = request.redirect("/web/login?oauth_error=2", 303)
            redirect.autocorrect_location_header = False
            return redirect
        return self._signin(
            dbname,
            claims["p"],
            kw,
            redirect=unquote_plus(claims["r"]) if claims.get("r") else None,
            signup_token=claims.get("t"),
        )

    def _signin(
        self, dbname, provider, kw, redirect=None, signup_token=None, context=None
    ):
        request.update_context(**clean_context(context or {}))
        try:
            # auth_oauth may create a new user, the commit makes it
            # visible to authenticate()'s own transaction below
            _, login, key = (
                request.env["res.users"]
                .with_user(SUPERUSER_ID)
                .auth_oauth(provider, kw, signup_token=signup_token)
            )
            request.env.cr.commit()

            credential = {"login": login, "token": key, "type": "oauth_token"}
            auth_info = request.session.authenticate(request.env, credential)
            resp = request.redirect(
                _get_login_redirect_url(auth_info["uid"], redirect), 303
            )
            resp.autocorrect_location_header = False

            # Since /web is hardcoded, verify user has right to land on it
            if (
                urlsplit(resp.location).path == "/web"
                and not request.env.user._is_internal()
            ):
                resp.location = "/"
            return resp
        except AttributeError:  # TODO juc master: useless since select_db()
            # auth_signup is not installed
            _logger.error(
                "auth_signup not installed on database %s: oauth sign up cancelled.",
                dbname,
            )
            url = "/web/login?oauth_error=1"
        except AccessDenied:
            # oauth credentials not valid, user could be on a temporary session
            _logger.info(
                "OAuth2: access denied, redirect to main page in case a valid session exists, without setting cookies"
            )
            url = "/web/login?oauth_error=3"
        except Exception:
            # signup error; a database error has aborted the transaction the
            # redirect's post-dispatch and commit still run on
            _logger.exception("Exception during request handling")
            request.env.cr.rollback()
            url = "/web/login?oauth_error=2"

        redirect = request.redirect(url, 303)
        redirect.autocorrect_location_header = False
        return redirect

    @http.route("/auth_oauth/oea", type="http", auth="none", readonly=False)
    def oea(self, **kw):
        """login user via Odoo Account provider"""
        dbname = kw.pop("db", None)
        if not dbname:
            dbname = request.db
        if not dbname:
            raise BadRequest
        if not request.app.filter_dbs_served([dbname]):
            raise BadRequest

        registry = Registry(dbname)
        with registry.cursor() as cr:
            try:
                env = api.Environment(cr, SUPERUSER_ID, {})
                provider = env.ref("auth_oauth.provider_odoo")
            except ValueError:
                redirect = request.redirect(f"/web?db={dbname}", 303)
                redirect.autocorrect_location_header = False
                return redirect
            assert provider._name == "auth.oauth.provider"

        select_db(db=dbname)
        return self._signin(
            dbname,
            provider.id,
            kw,
            redirect="/odoo",
            context={"no_user_creation": True},
        )
