import logging
from datetime import datetime, timedelta

import babel.dates

from odoo import models
from odoo.exceptions import AccessDenied, UserError
from odoo.http import request
from odoo.tools.misc import babel_locale_parse, hmac, register_signed_scope

from odoo.addons.auth_totp.models.totp import TOTP, hotp

_logger = logging.getLogger(__name__)

MAIL_CODE_SCOPE = register_signed_scope(
    "auth_totp_mail-code",
    purpose="the key the mailed two-factor codes of a user are derived from",
    lifetime="undated: it changes with the user's login date; each code lives "
    "its own TOTP window",
)


class ResUsers(models.Model):
    _inherit = "res.users"

    def write(self, vals):
        res = super().write(vals)

        if "totp_secret" in vals:
            if vals.get("totp_secret"):
                self._notify_security_setting_update(
                    self.env._("Security Update: 2FA Activated"),
                    self.env._(
                        "Two-factor authentication has been activated on your account"
                    ),
                    suggest_2fa=False,
                )
            else:
                self._notify_security_setting_update(
                    self.env._("Security Update: 2FA Deactivated"),
                    self.env._(
                        "Two-factor authentication has been deactivated on your account"
                    ),
                    suggest_2fa=False,
                )

        return res

    def authenticate(self, credential, user_agent_env):
        auth_info = super().authenticate(credential, user_agent_env)
        self._notify_security_new_connection(auth_info)
        return auth_info

    def _notify_security_new_connection(self, auth_info) -> None:
        user = self.env(user=auth_info["uid"]).user

        if request and user.email and user._get_mfa_type():
            key = request.cookies.get("td_id")
            if not key or not request.env["auth.totp.trust"]._resolve_trust_id(
                key=key, uid=user.id
            ):
                user._notify_security_setting_update(
                    subject=self.env._("New Connection to your Account"),
                    content=self.env._(
                        "A new device was used to sign in to your account."
                    ),
                )
                _logger.info(
                    "New device alert email sent for user <%s> to <%s>",
                    user.login,
                    user.email,
                )

    def _notify_security_setting_update_prepare_values(
        self, content, *, suggest_2fa=True, **kwargs
    ):

        values = super()._notify_security_setting_update_prepare_values(
            content, **kwargs
        )
        values["suggest_2fa"] = suggest_2fa and not self.totp_enabled
        return values

    def action_view_my_account_settings(self) -> dict:
        return {
            "name": self.env._("Security"),
            "type": "ir.actions.act_window",
            "res_model": "res.users",
            "views": [[self.env.ref("auth_totp_mail.res_users_view_form").id, "form"]],
            "res_id": self.id,
        }

    def get_totp_invite_url(self):
        return "/odoo/action-auth_totp_mail.action_activate_two_factor_authentication"

    def action_totp_invite(self) -> dict:
        invite_template = self.env.ref("auth_totp_mail.mail_template_totp_invite")
        users_to_invite = self.sudo().filtered(lambda user: not user.totp_secret)
        for user in users_to_invite:
            email_values = {
                "email_from": self.env.user.email_formatted,
                "author_id": self.env.user.partner_id.id,
            }
            invite_template.send_mail(
                user.id,
                force_send=True,
                email_values=email_values,
                email_layout_xmlid="mail.mail_notification_light",
            )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "info",
                "sticky": False,
                "message": self.env._(
                    "Invitation to use two-factor authentication sent for the following user(s): %s",
                    ", ".join(users_to_invite.mapped("name")),
                ),
            },
        }

    def _get_mfa_type(self):
        r = super()._get_mfa_type()
        if r is not None:
            return r
        ICP = self.env["ir.config_parameter"].sudo()
        otp_required = False
        if ICP.get_param("auth_totp.policy") == "all_required" or (
            ICP.get_param("auth_totp.policy") == "employee_required"
            and self._is_internal()
        ):
            otp_required = True
        if otp_required:
            return "totp_mail"
        return None

    def _get_mfa_url(self):
        r = super()._get_mfa_url()
        if r is not None:
            return r
        if self._get_mfa_type() == "totp_mail":
            return "/web/login/totp"
        return None

    def _is_rpc_api_key_only(self) -> bool:
        return bool(
            self._get_mfa_type() == "totp_mail" or super()._is_rpc_api_key_only()
        )

    def _authenticate_credentials(self, credentials, env):
        if credentials["type"] == "totp_mail":
            self._totp_rate_limit("code_check")
            user = self.sudo()
            key = user._get_totp_mail_key()
            match = TOTP(key).match(credentials["token"], window=3600, timestep=3600)
            if match is None:
                _logger.info("2FA check (mail): FAIL for %s %r", user, user.login)
                raise AccessDenied(
                    self.env._(
                        "Verification failed, please double-check the 6-digit code"
                    )
                )
            _logger.info("2FA check(mail): SUCCESS for %s %r", user, user.login)
            self._remove_totp_rate_limit_logs("code_check")
            self._remove_totp_rate_limit_logs("send_email")
            return {
                "uid": self.id,
                "auth_method": "totp_mail",
                "mfa": "default",
            }
        else:
            return super()._authenticate_credentials(credentials, env)

    def _get_totp_mail_key(self):
        self.check_singleton()
        return hmac(
            self.env(su=True),
            MAIL_CODE_SCOPE,
            (self.id, self.login, self.login_date),
        ).encode()

    def _get_totp_mail_code(self) -> tuple:
        self.check_singleton()

        key = self._get_totp_mail_key()

        now = datetime.now()
        counter = int(datetime.timestamp(now) / 3600)

        code = hotp(key, counter)
        expiration = timedelta(seconds=3600)
        lang = babel_locale_parse(self.env.context.get("lang") or self.lang)
        expiration = babel.dates.format_timedelta(expiration, locale=lang)

        return str(code).zfill(6), expiration

    def _send_totp_mail_code(self) -> None:
        self.check_singleton()
        self._totp_rate_limit("send_email")

        if not self.email:
            raise UserError(
                self.env._(
                    "Cannot send email: user %s has no email address.", self.name
                )
            )

        template = self.env.ref("auth_totp_mail.mail_template_totp_mail_code").sudo()
        context = {}
        if request:
            device = request.httprequest.user_agent.platform
            browser = request.httprequest.user_agent.browser
            context.update(
                {
                    "location": None,
                    "device": (device and device.capitalize()) or None,
                    "browser": (browser and browser.capitalize()) or None,
                    "ip": request.httprequest.remote_addr,
                }
            )
            if request.geoip.city.name:
                context["location"] = (
                    f"{request.geoip.city.name}, {request.geoip.country_name}"
                )

        email_values = {
            "email_to": self.email,
            "email_cc": False,
            "auto_delete": True,
            "recipient_ids": [],
            "partner_ids": [],
            "scheduled_date": False,
        }
        template.with_context(**context).send_mail(
            self.id,
            force_send=True,
            raise_exception=True,
            email_values=email_values,
            email_layout_xmlid="mail.mail_notification_light",
        )
