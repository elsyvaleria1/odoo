from odoo import api, models
from odoo.exceptions import UserError, ValidationError
from odoo.http import request
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)

# the request parameter every form sends its token in, whichever the provider
TOKEN_PARAM = "captcha_token"
# the setting's value that checks nothing, where an unset one picks a provider
NO_PROVIDER = "none"


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @api.model
    def _captcha_providers(self) -> dict:
        """{code: CaptchaProvider} of the installed providers."""
        return {}

    @api.model
    def _captcha_provider(self):
        """The provider chosen in the settings, when it is installed and has a
        site key; with none chosen, the first installed one, by code, that has
        a site key and a secret; None when the settings say none."""
        code = self.env.registry.settings.get(self.env, "captcha.provider", False)
        if code == NO_PROVIDER:
            return None
        providers = self._captcha_providers()
        if code:
            provider = providers.get(code)
            if provider and self.env[provider.adapter]._site_key():
                return provider
            return None
        for _code, provider in sorted(providers.items()):
            adapter = self.env[provider.adapter]
            if adapter._site_key() and adapter._has_secret():
                return provider
        return None

    def session_info(self):
        return self._add_captcha_to_session_info(super().session_info())

    @api.model
    def get_frontend_session_info(self):
        return self._add_captcha_to_session_info(super().get_frontend_session_info())

    @api.model
    def _add_captcha_to_session_info(self, session_info):
        if provider := self._captcha_provider():
            session_info["captcha"] = {
                "provider": provider.code,
                "site_key": self.env[provider.adapter]._site_key(),
            }
        return session_info

    @api.model
    def _check_request_captcha_token(self, action: str) -> None:
        super()._check_request_captcha_token(action)
        provider = self._captcha_provider()
        if not request or not provider:
            return
        token = request.params.pop(TOKEN_PARAM, False)
        verdict = self.env[provider.adapter]._verdict(
            request.httprequest.remote_addr, token, action
        )
        if verdict in ("is_human", "no_secret"):
            return
        _debug.logic("captcha_refused", provider=provider.code, verdict=verdict)
        if verdict == "wrong_secret":
            raise ValidationError(
                self.env._(
                    "The %(provider)s secret key is invalid.", provider=provider.label
                )
            )
        if verdict == "wrong_token":
            raise ValidationError(
                self.env._(
                    "The %(provider)s token is invalid.", provider=provider.label
                )
            )
        if verdict == "timeout":
            raise UserError(self.env._("Your request has timed out, please retry."))
        if verdict == "bad_request":
            raise UserError(self.env._("The request is invalid or malformed."))
        raise UserError(
            self.env._(
                "Suspicious activity detected by %(provider)s.", provider=provider.label
            )
        )
