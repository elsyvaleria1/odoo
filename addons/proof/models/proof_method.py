from typing import Any

from odoo import fields, models
from odoo.exceptions import AccessDenied, UserError
from odoo.tools import frozendict

STRENGTHS = [
    ("cryptographic", "Signed by the user's own key"),
    ("device_attested", "Reported by a trusted device"),
    ("shared_secret", "Secret shared with the server"),
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
        "only the user holds, a device the server trusts, or a secret the server "
        "can check.",
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

    def _get_proof_options(self, challenge: models.BaseModel) -> dict[str, Any]:
        self.check_singleton()
        return {}

    def _accept_proof(
        self, challenge: models.BaseModel, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Check the user's proof against the challenge and return what the
        evidence keeps of it; raise UserError when it does not hold."""
        self.check_singleton()
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
            with user._assert_can_auth(user=user.id):
                user._check_credentials(credential, {"interactive": True})
        except AccessDenied:
            raise UserError(self.env._("Incorrect password.")) from None
