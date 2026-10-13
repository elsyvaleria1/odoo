import re

from odoo import http
from odoo.exceptions import AccessDenied
from odoo.http import request

from odoo.addons.web.controllers import home as web_home

TRUSTED_DEVICE_COOKIE = "td_id"
TRUSTED_DEVICE_AGE_DAYS = 90


class Home(web_home.Home):
    @http.route(
        "/web/login/totp",
        type="http",
        auth="public",
        methods=["GET", "POST"],
        sitemap=False,
        website=True,
        multilang=False,
    )
    def web_totp(self, redirect=None, **kwargs):
        if request.session.uid:
            return request.redirect(
                self._login_redirect(request.session.uid, redirect=redirect)
            )

        if not request.session.get("pre_uid"):
            return request.redirect("/web/login")

        error = None

        user = request.env["res.users"].sudo().browse(request.session["pre_uid"])
        if user and request.httprequest.method == "GET":
            cookies = request.cookies
            key = cookies.get(TRUSTED_DEVICE_COOKIE)
            if key:
                user_match = request.env["auth.totp.trust"]._resolve_trust_id(
                    key=key, uid=user.id
                )
                if user_match:
                    request.session["pre_totp_trust_id"] = user_match
                    request.session.finalize_login(request.env)
                    request.update_env(user=request.session.uid)
                    request.update_context(**request.session.context)
                    return request.redirect(
                        self._login_redirect(request.session.uid, redirect=redirect)
                    )

        elif user and request.httprequest.method == "POST" and kwargs.get("totp_token"):
            try:
                with user._admit_authentication_attempt(user=user.id):
                    credentials = {
                        "type": user._get_mfa_type(),
                        "token": int(re.sub(r"\s", "", kwargs["totp_token"])),
                    }
                    user._authenticate_credentials(credentials, {"interactive": True})
            except AccessDenied as e:
                error = str(e)
            except ValueError:
                error = request.env._("Invalid authentication code format.")
            else:
                request.session.finalize_login(request.env)
                request.update_env(user=request.session.uid)
                request.update_context(**request.session.context)
                response = request.redirect(
                    self._login_redirect(request.session.uid, redirect=redirect)
                )
                if kwargs.get("remember"):
                    user_agent = request.httprequest.user_agent
                    name = request.env._(
                        "%(browser)s on %(platform)s",
                        browser=(
                            user_agent.browser.capitalize()
                            if user_agent.browser
                            else request.env._("Unknown browser")
                        ),
                        platform=(
                            user_agent.platform.capitalize()
                            if user_agent.platform
                            else request.env._("Unknown platform")
                        ),
                    )

                    if request.geoip.city.name:
                        name += f" ({request.geoip.city.name}, {request.geoip.country_name})"

                    trusted_device_age = request.env[
                        "auth.totp.trust"
                    ]._get_trusted_device_age()
                    trust, key = request.env["auth.totp.trust"]._issue(name)
                    request.env["auth.user.client"]._trust_current_client(trust.id)
                    response.set_cookie(
                        key=TRUSTED_DEVICE_COOKIE,
                        value=key,
                        max_age=trusted_device_age,
                        httponly=True,
                        samesite="Lax",
                    )
                request.session.mark_dirty()
                return response

        request.session.mark_dirty()
        return request.render(
            "auth_totp.auth_totp_form",
            {
                "user": user,
                "error": error,
                "redirect": redirect,
            },
        )
