from werkzeug.exceptions import BadRequest

from odoo import http
from odoo.http import request
from odoo.tools import consume_session_state, issue_session_state, register_signed_scope

_OAUTH_STATE_MAX_AGE_SECONDS = 1800

OAUTH_STATE_SCOPE = register_signed_scope(
    "google_account.oauth_state",
    purpose="the state a Google authorization carries through Google's consent "
    "page back to /google_account/authentication: the service and the return URL, bound "
    "to the database, user and session that started it",
    lifetime=f"its expiry: the callback refuses a state older than "
    f"{_OAUTH_STATE_MAX_AGE_SECONDS} seconds, or one already consumed",
)


def issue_oauth_state(env, service, from_url):
    return issue_session_state(
        env,
        OAUTH_STATE_SCOPE,
        request.session,
        {"s": service, "f": from_url},
        max_age_seconds=_OAUTH_STATE_MAX_AGE_SECONDS,
    )


class GoogleAuth(http.Controller):
    @http.route("/google_account/authentication", type="http", auth="public")
    def oauth2callback(self, **kw):
        """This route/function is called by Google when user Accept/Refuse the consent of Google"""
        claims = consume_session_state(
            request.env, OAUTH_STATE_SCOPE, request.session, kw.get("state")
        )
        if claims is None:
            raise BadRequest(
                request.env._(
                    "The Google authorization state is invalid, expired or already "
                    "used. Please start the synchronization again."
                )
            )
        service = claims.get("s")
        url_return = claims.get("f")
        if not service or (kw.get("code") and not url_return):
            raise BadRequest

        if kw.get("code"):
            base_url = (
                request.httprequest.url_root.strip("/")
                or request.env.user.get_base_url()
            )
            access_token, refresh_token, ttl = request.env[
                "google.service"
            ]._get_google_tokens(
                kw["code"],
                service,
                redirect_uri=f"{base_url}/google_account/authentication",
            )
            service_field = "res_users_settings_id"
            if service_field in request.env.user:
                request.env.user[service_field]._set_google_auth_tokens(
                    access_token, refresh_token, ttl
                )
            else:
                raise Warning("No callback field for service <%s>" % service)
            return request.redirect(url_return)
        elif kw.get("error"):
            return request.redirect("%s%s%s" % (url_return, "?error=", kw["error"]))
        else:
            return request.redirect("%s%s" % (url_return, "?error=Unknown_error"))
