import logging

import requests

from odoo import api, models

_logger = logging.getLogger(__name__)

# How much of a refused token reaches the log: the value is attacker-controlled
# and bounded only by the request size, so a prefix correlates without letting
# a caller choose how much is written.
TOKEN_LOG_PREFIX = 12


class CaptchaAdapter(models.AbstractModel):
    """A captcha provider's verification. A provider's adapter inherits this
    model under its own name; one answering the common siteverify protocol
    (reCAPTCHA, Turnstile) supplies its site key, its secret and the request."""

    _name = "captcha.adapter"
    _description = "Captcha Provider Adapter"

    @api.model
    def _site_key(self) -> str | None:
        """The key the browser script runs with; None when not configured."""
        raise NotImplementedError

    @api.model
    def _secret(self) -> str | None:
        raise NotImplementedError

    @api.model
    def _post_verification(self, data: dict) -> requests.Response:
        """Send `data` to the provider's siteverify endpoint."""
        raise NotImplementedError

    @api.model
    def _verdict(self, ip_addr: str, token, action: str) -> str:
        """The provider's verdict on `token`, sent from `ip_addr` for `action`:
        is_human, is_bot, no_secret, wrong_secret, wrong_token, wrong_action,
        timeout or bad_request."""
        secret = self._secret()
        if not secret:
            return "no_secret"
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
            # the class, not the message, which could echo what was sent: it
            # tells a TLS error from a parse error from an answer of another shape
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
        """The verdict on a token the provider accepted: a token obtained for
        another action does not prove this one."""
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
