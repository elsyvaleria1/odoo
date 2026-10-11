import logging
import re
import time
from typing import Any

from odoo import api, models
from odoo.http import SessionExpiredException, request, root
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class CheckIdentityException(SessionExpiredException):
    """Exception raised when a user is requested to re-authenticate."""

    loglevel = logging.DEBUG


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @classmethod
    def _get_identity_check_requirement(cls) -> dict[str, Any] | None:
        session = request.session
        env = request.env(user=request.session.uid)
        timeouts = env.user._get_lock_timeouts()
        for (
            timeout_type,
            reauth_type,
            session_key,
            session_key_default,
            first_timeout,
        ) in [
            ("lock_timeout", "logout", "create_time", 0, 0),
            (
                "lock_timeout_inactivity",
                "check_identity",
                "identity-check-next",
                None,
                timeouts["lock_timeout_inactivity"][0][0]
                if timeouts.get("lock_timeout_inactivity")
                else 0,
            ),
        ]:
            for timeout, mfa in reversed(timeouts[timeout_type]):
                threshold = time.time() - timeout
                timestamp = session.get(session_key, session_key_default)
                _debug.logic(
                    "identity_check_evaluated",
                    kind=timeout_type,
                    timeout=timeout,
                    timestamp=timestamp,
                    threshold=threshold,
                    first_timeout=first_timeout,
                )
                if timestamp is not None and timestamp - first_timeout <= threshold:
                    res = {reauth_type: True, "mfa": mfa}
                    if mfa:
                        first_fa = session.get("identity-check-1fa")
                        if first_fa:
                            timestamp_1fa, auth_method_1fa = first_fa
                            if timestamp_1fa > threshold:
                                res["1fa"] = auth_method_1fa
                    return res
        return None

    @classmethod
    def _check_identity(cls, credential):
        check_identity = cls._get_identity_check_requirement() or {}
        first_fa = check_identity.get("1fa")
        user = request.env.user
        auth_methods = user._get_auth_methods()
        if not credential:
            if first_fa and first_fa in auth_methods:
                auth_methods.remove(first_fa)
            return {
                "user_id": user.id,
                "login": user.login,
                "auth_methods": auth_methods,
            }

        if credential.get("type") in ("totp", "totp_mail"):
            credential["token"] = int(re.sub(r"\s", "", credential["token"]))

        with user._assert_can_auth(user=user.id):
            auth = user._check_credentials(credential, {"interactive": True})

        if first_fa and first_fa != auth["auth_method"]:
            request.session.pop("identity-check-1fa")
        elif (
            auth["mfa"] != "skip"
            and len(auth_methods) > 1
            and check_identity.get("mfa")
        ):
            request.session["identity-check-1fa"] = (time.time(), credential["type"])
            auth_methods.remove(credential["type"])
            return {"mfa": True, "auth_methods": auth_methods}

        request.session.pop("identity-check-next", None)
        request.session["identity-check-last"] = time.time()
        return None

    def _set_session_inactivity(
        self, session, inactivity_period=0, force=False
    ) -> None:
        inactivity_period /= 1000
        timeout = self.env.user._get_lock_timeout_inactivity()
        inactive = timeout and (force or inactivity_period >= timeout)
        _debug.lifecycle(
            "session_inactivity_reported",
            uid=self.env.uid,
            inactivity_s=inactivity_period,
            timeout=timeout,
            force=force,
            inactive=bool(inactive),
            next_check=session.get("identity-check-next"),
        )
        if inactive:
            next_check = time.time() + timeout - inactivity_period
            if (
                not session.get("identity-check-next")
                or next_check < session["identity-check-next"]
            ):
                session["identity-check-next"] = next_check
                root.session_store.save(session)
        elif (
            not inactive
            and (timestamp := session.get("identity-check-next"))
            and timestamp > time.time()
        ):
            session.pop("identity-check-next")
            root.session_store.save(session)

    @classmethod
    def _authenticate(cls, endpoint):
        super()._authenticate(endpoint)
        if endpoint.routing["auth"] == "user" and request.session.uid is not None:
            if must_check_identity := cls._get_identity_check_requirement():
                if must_check_identity.get("logout"):
                    raise SessionExpiredException(
                        f"User {request.session.uid} needs to login again"
                    )
                if endpoint.routing.get(
                    "check_identity", True
                ) and must_check_identity.get("check_identity"):
                    raise CheckIdentityException(
                        f"User {request.session.uid} needs to confirm his identity"
                    )

    @classmethod
    def _handle_error(cls, exception):
        if request.dispatcher.routing_type == "http" and isinstance(
            exception, CheckIdentityException
        ):
            return request.redirect_query(
                "/auth-timeout/check-identity",
                {"redirect": request.httprequest.full_path},
            )
        return super()._handle_error(exception)

    def _session_info_common_auth_timeout(self, session_info):
        if not self.env.user._is_public() and (
            timeout := self.env.user._get_lock_timeout_inactivity()
        ):
            session_info["lock_timeout_inactivity"] = timeout
        return session_info

    def session_info(self):
        session_info = super().session_info()
        return self._session_info_common_auth_timeout(session_info)

    @api.model
    def get_frontend_session_info(self):
        session_info = super().get_frontend_session_info()
        return self._session_info_common_auth_timeout(session_info)
