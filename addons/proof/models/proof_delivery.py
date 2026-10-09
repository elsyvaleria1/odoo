from typing import Any

from odoo import fields, models
from odoo.exceptions import UserError
from odoo.tools import frozendict

from .proof_method import VERDICTS

REASON_MAX_LENGTH = 2000


class ProofDelivery(models.Model):
    _name = "proof.delivery"
    _description = "Proof Confirmation Message"
    _order = "id desc"
    _access_anchors = frozendict({"company": ""})

    challenge_id = fields.Many2one(
        comodel_name="proof.challenge",
        index=True,
        readonly=True,
        required=True,
        ondelete="cascade",
    )
    method_id = fields.Many2one(
        comodel_name="proof.method",
        string="Method",
        readonly=True,
        required=True,
        ondelete="cascade",
    )
    partner_id = fields.Many2one(
        related="challenge_id.partner_id",
    )
    sent_to = fields.Char(
        readonly=True,
        help="Where the message went, masked.",
    )
    address = fields.Char(
        readonly=True,
        help="The channel's own id of the chat or address the message went to, "
        "which an answer must come from.",
    )
    ref = fields.Char(
        string="Message Reference",
        index="btree_not_null",
        readonly=True,
        help="The channel's own id of the message, which an answer replies to.",
    )
    state = fields.Selection(
        selection=[
            ("sent", "Sent"),
            ("answered", "Answered"),
            ("withdrawn", "Withdrawn"),
        ],
        default="sent",
        readonly=True,
        required=True,
    )

    def _answer(
        self,
        verdict: str,
        reason: str = "",
        payload: dict[str, Any] | None = None,
        signer_request: bool = True,
    ) -> models.BaseModel:
        """Record the contact's answer to the message, and return the evidence.

        ``signer_request`` says the current HTTP request is the contact's own,
        so its address and browser are theirs; a channel that relays answers
        server to server passes False."""
        self.check_singleton()
        if verdict not in dict(VERDICTS):
            raise UserError(self.env._("This answer is not one we asked for."))
        delivery = self.with_env(
            self.env["proof.challenge"]._with_proof_privilege().env
        )
        challenge = delivery.challenge_id
        if (
            delivery.state != "sent"
            or challenge.state != "issued"
            or challenge.date_expire < fields.Datetime.now()
        ):
            raise UserError(
                self.env._("This request was already answered or is no longer current.")
            )
        accepted = {
            **(payload or {}),
            "channel": delivery.method_id.code,
            "sent_to": delivery.sent_to,
            "delivery": delivery.id,
        }
        reason = (reason or "").strip()[:REASON_MAX_LENGTH]
        if reason:
            accepted["reason"] = reason
        delivery.state = "answered"
        evidence = challenge._record_answer(
            delivery.method_id,
            accepted,
            verdict,
            signer_request=signer_request,
        )
        challenge._withdraw_deliveries()
        challenge._notify_record("_on_confirmation_answered", evidence)
        return self.env["proof.evidence"].browse(evidence.id)
