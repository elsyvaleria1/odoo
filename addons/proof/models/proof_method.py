from typing import Any

from odoo import fields, models
from odoo.exceptions import AccessDenied, UserError
from odoo.tools import SQL, frozendict, register_signed_scope
from odoo.tools.security import is_hmac_valid

CODE_SCOPE = register_signed_scope(
    "proof_code",
    purpose="a one-time code sent to the signer's own channel answers one proof "
    "challenge",
    lifetime="the challenge's own: it is checked only while the challenge is "
    "issued and unexpired",
)
CODE_DIGITS = 6
CODE_ATTEMPTS = 5
CODE_LOCK = 20251009

STRENGTHS = [
    ("cryptographic", "Signed by the user's own key"),
    ("device_attested", "Reported by a trusted device"),
    ("shared_secret", "Secret shared with the server"),
    ("possession", "Code delivered to the signer's own channel"),
]
VERDICTS = [
    ("confirmed", "Confirmed"),
    ("disputed", "Disputed"),
]
MODES = [
    ("submit", "Answered in the dialog"),
    ("confirm", "Answered on the contact's own channel"),
]


class ProofMethod(models.Model):
    _name = "proof.method"
    _description = "Proof Method"
    _order = "sequence, id"
    _access_anchors = frozendict({"company": ""})

    name = fields.Char(
        translate=True,
        required=True,
    )
    code = fields.Selection(
        selection=[("password", "Password")],
        readonly=True,
        required=True,
    )
    strength = fields.Selection(
        selection=STRENGTHS,
        readonly=True,
        required=True,
        help="What an accepted proof of this method rests on: a signature by a key "
        "only the user holds, a device the server trusts, a secret the server "
        "can check, or a code only the signer's own email or phone received.",
    )
    mode = fields.Selection(
        selection=MODES,
        default="submit",
        readonly=True,
        required=True,
        help="Answered in the dialog: the user, or a contact through them, gives "
        "the proof on the screen that asked for it. Answered on the contact's own "
        "channel: the contact receives what they are asked to confirm and "
        "answers it there, on their own time.",
    )
    sequence = fields.Integer(
        default=10,
    )
    active = fields.Boolean(
        default=True,
    )

    _code_uniq = models.Constraint(
        "unique(code)",
        "Each proof method is declared once.",
    )

    def _is_enrolled(self, user: models.BaseModel) -> bool:
        self.check_singleton()
        return self.code == "password"

    def _is_enrolled_contact(self, partner: models.BaseModel) -> bool:
        self.check_singleton()
        return False

    def _deliver_confirmation(
        self, challenge: models.BaseModel, reminder: bool = False
    ) -> models.BaseModel:
        self.check_singleton()
        raise UserError(
            self.env._(
                "The proof method %(method)s is not available.", method=self.name
            )
        )

    def _withdraw_delivery(self, delivery: models.BaseModel) -> None:
        self.check_singleton()

    def _uses_code(self) -> bool:
        self.check_singleton()
        return False

    def _send_code(
        self, challenge: models.BaseModel, signer: models.BaseModel, code: str
    ) -> str:
        self.check_singleton()
        raise UserError(
            self.env._(
                "The proof method %(method)s is not available.", method=self.name
            )
        )

    def _get_proof_options(self, challenge: models.BaseModel) -> dict[str, Any]:
        self.check_singleton()
        return {}

    def _check_code(
        self, challenge: models.BaseModel, payload: dict[str, Any]
    ) -> dict[str, Any]:
        code = payload.get("code")
        right = bool(challenge.code_hash) and is_hmac_valid(
            self.env, CODE_SCOPE, (challenge.id, code), challenge.code_hash
        )
        if not self._take_code_attempt(challenge, wrong=not right):
            raise UserError(
                self.env._("Too many wrong codes. Start again to send a new one.")
            )
        if not right:
            raise UserError(self.env._("This code is not the one we sent."))
        signer = challenge.partner_id or challenge.user_id.partner_id
        return {
            "channel": self.code,
            "sent_to": challenge.code_sent_to,
            "signer": signer.id,
        }

    def _take_code_attempt(self, challenge: models.BaseModel, wrong: bool) -> bool:
        with self.env.registry.cursor() as cr:
            cr.execute(
                SQL("SELECT pg_advisory_xact_lock(%s, %s)", CODE_LOCK, challenge.id)
            )
            cr.execute(
                SQL(
                    "SELECT COALESCE(code_attempts, 0) FROM proof_challenge "
                    "WHERE id = %s",
                    challenge.id,
                )
            )
            row = cr.fetchone()
            takes = bool(row) and row[0] < CODE_ATTEMPTS
            if takes and wrong:
                cr.execute(
                    SQL(
                        "UPDATE proof_challenge "
                        "SET code_attempts = COALESCE(code_attempts, 0) + 1 "
                        "WHERE id = %s",
                        challenge.id,
                    )
                )
        challenge.invalidate_recordset(["code_attempts"])
        return takes

    def _count_wrong_code(self, challenge: models.BaseModel) -> None:
        self._take_code_attempt(challenge, wrong=True)

    def _accept_proof(
        self, challenge: models.BaseModel, payload: dict[str, Any]
    ) -> dict[str, Any]:
        self.check_singleton()
        if self._uses_code():
            return self._check_code(challenge, payload)
        if self.code == "password":
            self._check_password(payload.get("password"))
            return {}
        raise UserError(
            self.env._(
                "The proof method %(method)s is not available.", method=self.name
            )
        )

    def _check_password(self, password: Any) -> None:
        user = self.env.user
        credential = {
            "login": user.login,
            "password": password if isinstance(password, str) else "",
            "type": "password",
        }
        try:
            with user._admit_authentication_attempt(user=user.id):
                user._authenticate_credentials(credential, {"interactive": True})
        except AccessDenied:
            raise UserError(self.env._("Incorrect password.")) from None
