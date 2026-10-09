import base64
import logging
from hashlib import sha256
from typing import Any

from odoo import fields, models
from odoo.exceptions import AccessDenied, UserError

_logger = logging.getLogger(__name__)


class ProofMethod(models.Model):
    _inherit = "proof.method"

    code = fields.Selection(
        selection_add=[("passkey", "Passkey")],
        ondelete={"passkey": "cascade"},
    )

    def _is_enrolled(self, user: models.BaseModel) -> bool:
        self.check_singleton()
        if self.code == "passkey":
            return bool(user.auth_passkey_key_ids)
        return super()._is_enrolled(user)

    def _get_proof_options(self, challenge: models.BaseModel) -> dict[str, Any]:
        self.check_singleton()
        if self.code == "passkey":
            return self.env["auth.passkey.key"]._get_own_authentication_options(
                self._get_passkey_challenge(challenge)
            )
        return super()._get_proof_options(challenge)

    def _accept_proof(
        self, challenge: models.BaseModel, payload: dict[str, Any]
    ) -> dict[str, Any]:
        self.check_singleton()
        if self.code != "passkey":
            return super()._accept_proof(challenge, payload)
        credential = payload.get("credential")
        if not isinstance(credential, dict):
            raise UserError(self.env._("No passkey answered this request."))
        signed = self._get_passkey_challenge(challenge)
        try:
            accepted = self.env["auth.passkey.key"]._accept_own_assertion(
                credential, signed
            )
        except AccessDenied as error:
            _logger.info("Passkey proof refused for user #%s: %s", self.env.uid, error)
            raise UserError(
                self.env._("Your passkey did not confirm this request.")
            ) from None
        response = credential.get("response") or {}
        return {
            **accepted,
            "challenge": base64.urlsafe_b64encode(signed).decode().rstrip("="),
            "authenticator_data": response.get("authenticatorData"),
            "client_data_json": response.get("clientDataJSON"),
            "signature": response.get("signature"),
            "user_handle": response.get("userHandle"),
        }

    def _get_passkey_challenge(self, challenge: models.BaseModel) -> bytes:
        # one-time (the token's hash) and bound to the figures (the digest):
        # the authenticator signs over it, so the signature covers both
        challenge.check_singleton()
        return sha256(f"{challenge.token_hash}:{challenge.digest}".encode()).digest()
