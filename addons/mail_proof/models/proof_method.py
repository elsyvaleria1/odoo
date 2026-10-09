import logging
import secrets
from typing import Any

from odoo import fields, models
from odoo.exceptions import UserError
from odoo.tools import SQL, register_signed_scope
from odoo.tools.security import hmac, is_hmac_valid

_logger = logging.getLogger(__name__)

CODE_SCOPE = register_signed_scope(
    "mail_proof_code",
    purpose="a one-time code sent by email answers one proof challenge",
    lifetime="the challenge's own: it is checked only while the challenge is "
    "issued and unexpired",
)
CODE_DIGITS = 6
CODE_ATTEMPTS = 5


class ProofMethod(models.Model):
    _inherit = "proof.method"

    code = fields.Selection(
        selection_add=[("email_code", "Email Code")],
        ondelete={"email_code": "cascade"},
    )

    def _is_enrolled(self, user: models.BaseModel) -> bool:
        self.check_singleton()
        if self.code == "email_code":
            return bool(user.email_normalized)
        return super()._is_enrolled(user)

    def _is_enrolled_contact(self, partner: models.BaseModel) -> bool:
        self.check_singleton()
        if self.code == "email_code":
            return bool(partner.email_normalized)
        return super()._is_enrolled_contact(partner)

    def _get_proof_options(self, challenge: models.BaseModel) -> dict[str, Any]:
        self.check_singleton()
        if self.code != "email_code":
            return super()._get_proof_options(challenge)
        signer = challenge.partner_id or challenge.user_id.partner_id
        code = f"{secrets.randbelow(10**CODE_DIGITS):0{CODE_DIGITS}d}"
        sent_to = self._mask_email(signer.email_normalized)
        challenge.write(
            {
                "code_hash": hmac(self.env, CODE_SCOPE, (challenge.id, code)),
                "code_sent_to": sent_to,
            }
        )
        self._send_code(challenge, signer, code)
        return {"sent_to": sent_to, "digits": CODE_DIGITS}

    def _send_code(
        self, challenge: models.BaseModel, signer: models.BaseModel, code: str
    ) -> None:
        lang = signer.lang or self.env.lang
        body = (
            self.env["ir.qweb"]
            .with_context(lang=lang)
            ._render(
                "mail_proof.email_code_body",
                {
                    "code": code,
                    "signer": signer,
                    "asker": challenge.user_id,
                    "summary": challenge.summary or [],
                },
            )
        )
        mail = (
            self.env["mail.mail"]
            .with_privilege(
                "mail_proof.privilege_send_proof_code",
                reason="a proof request mails its one-time code to the signer",
            )
            .create(
                {
                    "subject": self.with_context(lang=lang).env._(
                        "Your confirmation code"
                    ),
                    "email_from": self.env.company.email_formatted
                    or challenge.user_id.email_formatted,
                    "email_to": signer.email_formatted,
                    "body_html": body,
                    "auto_delete": True,
                }
            )
        )
        # sent now: the signer stands at the counter waiting for it
        mail.send(raise_exception=False)

    def _accept_proof(
        self, challenge: models.BaseModel, payload: dict[str, Any]
    ) -> dict[str, Any]:
        self.check_singleton()
        if self.code != "email_code":
            return super()._accept_proof(challenge, payload)
        if challenge.code_attempts >= CODE_ATTEMPTS:
            raise UserError(
                self.env._("Too many wrong codes. Start again to send a new one.")
            )
        code = payload.get("code")
        if not challenge.code_hash or not is_hmac_valid(
            self.env, CODE_SCOPE, (challenge.id, code), challenge.code_hash
        ):
            self._count_wrong_code(challenge)
            raise UserError(self.env._("This code is not the one we sent."))
        signer = challenge.partner_id or challenge.user_id.partner_id
        return {
            "channel": "email",
            "sent_to": challenge.code_sent_to,
            "signer": signer.id,
        }

    def _count_wrong_code(self, challenge: models.BaseModel) -> None:
        # in its own transaction, since the refusal rolls this request back;
        # only a wrong code counts, so the request that redeems the challenge
        # is never the one that also moved its counter
        with self.env.registry.cursor() as cr:
            cr.execute(
                SQL(
                    "UPDATE proof_challenge "
                    "SET code_attempts = COALESCE(code_attempts, 0) + 1 "
                    "WHERE id = %s",
                    challenge.id,
                )
            )
        challenge.invalidate_recordset(["code_attempts"])

    def _mask_email(self, email: str) -> str:
        local, _at, domain = (email or "").partition("@")
        return f"{local[:1]}{'*' * max(len(local) - 1, 1)}@{domain}"
