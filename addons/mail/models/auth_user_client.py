from odoo import models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class AuthUserClient(models.Model):
    _inherit = "auth.user.client"

    def _notify_new_client(self) -> None:
        super()._notify_new_client()
        self.check_singleton()
        user = self.user_id
        if not user.email or not self.browser:
            _debug.logic(
                "new_device_alert_skipped",
                reason="no_email_or_browser",
                email=bool(user.email),
                browser=self.browser,
                platform=self.platform,
            )
            return
        if user._get_mfa_type():
            _debug.logic("new_device_alert_skipped", reason="mfa")
            return
        if not self.with_context(active_test=False).search_count(
            [("user_id", "=", user.id), ("id", "!=", self.id)], limit=1
        ):
            _debug.logic("new_device_alert_skipped", reason="first_device")
            return
        owner = self.with_context(lang=user.lang)
        user.with_context(lang=user.lang)._notify_security_setting_update(
            subject=owner.env._("New Sign-in to your Account"),
            content=owner.env._(
                "A device never used before, %(device)s, signed in to your account.",
                device=owner.display_name,
            ),
        )
        _debug.lifecycle("new_device_alert_sent", user=user.id, device=self.id)
