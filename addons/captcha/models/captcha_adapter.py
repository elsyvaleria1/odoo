import logging

import requests

from odoo import api, models

_logger = logging.getLogger(__name__)

TOKEN_LOG_PREFIX = 12


class CaptchaAdapter(models.AbstractModel):

    _name = "captcha.adapter"
    _description = "Captcha Provider Adapter"

    @api.model
    def _site_key(self) -> str | None:
        raise NotImplementedError

    @api.model
    def _secret(self) -> str | None:
        raise NotImplementedError

    @api.model
    def _has_secret(self) -> bool:
        raise NotImplementedError

    @api.model
    def _post_verification(self, data: dict) -> requests.Response:
        raise NotImplementedError

    @api.model
    def _verdict(self, ip_addr: str, token, action: str) -> str:
        secret = self._secret()
        if not secret:
            return "no_secret"
        if not token:
            return "wrong_token"
        try:
            response = self._post_verification(
                {"secret": secret, "response": token, "remoteip": ip_addr}
            )
            result = response.json()
            success = result["success"]
        except requests.exceptions.Timeout:
            _logger.error("captcha verification timed out for ip address %s", ip_addr)
            return "timeout"
        except (
            requests.exceptions.RequestException,
            ValueError,
            KeyError,
            TypeError,
        ) as error:
            _logger.error(
                "captcha verification got a malformed answer (%s)",
                type(error).__name__,
            )
            return "bad_request"
        if success:
            return self._verdict_of_success(ip_addr, result, action)
        errors = result.get("error-codes", [])
        _logger.warning(
            "captcha verification for ip address %s failed with error codes %r; "
            "token prefix [%s]",
            ip_addr,
            errors,
            (token or "")[:TOKEN_LOG_PREFIX],
        )
        for error in errors:
            if error in ("missing-input-secret", "invalid-input-secret"):
                return "wrong_secret"
            if error in ("missing-input-response", "invalid-input-response"):
                return "wrong_token"
            if error in ("timeout-or-duplicate", "internal-error"):
                return "timeout"
            if error == "bad-request":
                return "bad_request"
        return "is_bot"

    @api.model
    def _verdict_of_success(self, ip_addr: str, result: dict, action: str) -> str:
        if action and result.get("action") and result["action"] != action:
            _logger.warning(
                "captcha verification for ip address %s was for action %s, not %s",
                ip_addr,
                result["action"],
                action,
            )
            return "wrong_action"
        _logger.info("captcha verification for ip address %s succeeded", ip_addr)
        return "is_human"
