from datetime import timedelta
from typing import Any

from odoo import api, fields, models
from odoo.exceptions import UserError

from .proof_challenge import CONFIRMATION_LIFETIME

CONFIRMATION_STATES = [
    ("pending", "Waiting for the Contact"),
    ("unreachable", "Contact Unreachable"),
    ("confirmed", "Confirmed"),
    ("disputed", "Disputed"),
    ("expired", "Not Answered"),
]
REMINDER_DELAY = timedelta(days=1)


class MixinProofConfirmation(models.AbstractModel):
    """A record its contact confirms: what they gave or received, stated to them
    on their own channel, answered there with Confirm or Not right; or, with the
    contact at the counter, proven with a code they received."""

    _name = "mixin.proof.confirmation"
    _description = "Contact Confirmation"

    confirmation_challenge_ids = fields.One2many(
        comodel_name="proof.challenge",
        inverse_name="res_id",
        string="Confirmation Requests",
        copy=False,
        readonly=True,
        classification="base.internal",
        groups="base.group_system",
    )
    confirmation_state = fields.Selection(
        selection=CONFIRMATION_STATES,
        string="Contact Confirmation",
        compute="_compute_confirmation_state",
        store=True,
        index="btree_not_null",
        copy=False,
        readonly=True,
        discloses="base.internal",
    )
    confirmation_date = fields.Datetime(
        string="Answered On",
        compute="_compute_confirmation_state",
        store=True,
        copy=False,
        readonly=True,
        discloses="base.internal",
    )
    confirmation_sent_to = fields.Char(
        string="Answered From",
        compute="_compute_confirmation_state",
        store=True,
        copy=False,
        readonly=True,
        discloses="base.internal",
        help="The channel the contact answered on, masked.",
    )

    @api.depends(
        "confirmation_challenge_ids.state",
        "confirmation_challenge_ids.delivery_ids.state",
    )
    def _compute_confirmation_state(self) -> None:
        deciding = self._get_confirmation_challenges()
        for record in self:
            challenge = deciding.get(record.id)
            evidence = challenge.evidence_id if challenge else None
            record.confirmation_state = (
                record._get_confirmation_state_from(challenge) if challenge else False
            )
            record.confirmation_date = evidence.date if evidence else False
            record.confirmation_sent_to = (
                (evidence.payload or {}).get("sent_to") if evidence else False
            )

    def _get_confirmation_state_from(self, challenge: models.BaseModel) -> str:
        if challenge.state == "redeemed":
            return challenge.verdict or "confirmed"
        if challenge.state == "expired":
            return "expired"
        if any(delivery.state == "sent" for delivery in challenge.delivery_ids):
            return "pending"
        return "unreachable"

    def _get_confirmation_challenges(self) -> dict[int, models.BaseModel]:
        """The challenge that decides each record's confirmation: its latest one
        still standing, a code at the counter counting once it was given."""
        ids = [id_ for id_ in self.ids if isinstance(id_, int)]
        if not ids:
            return {}
        challenges = (
            self.env["proof.challenge"]
            ._with_proof_privilege()
            .search(
                [
                    ("res_model", "=", self._name),
                    ("res_id", "in", ids),
                    ("purpose", "=", self._get_confirmation_purpose()),
                    ("state", "!=", "withdrawn"),
                ],
                order="id desc",
            )
        )
        deciding = {}
        for challenge in challenges:
            if challenge.kind == "submit" and challenge.state != "redeemed":
                continue
            deciding.setdefault(challenge.res_id, challenge)
        return deciding

    def _get_confirmation_partner(self) -> models.BaseModel:
        """The contact who confirms the record; none, and nobody is asked."""
        return self.env["res.partner"]

    def _get_confirmation_purpose(self) -> str:
        return f"{self._name}.confirmation"

    def _get_confirmation_facts(self) -> dict[str, Any]:
        """Every figure the contact confirms, JSON-serialisable."""
        raise NotImplementedError

    def _get_confirmation_summary(self) -> list[list[str]]:
        """What the contact is shown, as label/value pairs, in their language."""
        raise NotImplementedError

    def _get_confirmation_links(self) -> list[tuple[str, str]]:
        """Links sent along with what the contact confirms, as label/URL pairs
        in their language: their receipt, for instance."""
        return []

    def _get_confirmation_lifetime(self) -> timedelta:
        return CONFIRMATION_LIFETIME

    def _get_confirmation_reminder_delay(self) -> timedelta | None:
        return REMINDER_DELAY

    def _ask_confirmation(self) -> None:
        """Ask each record's contact to confirm it, taking back what they were
        asked before."""
        self._withdraw_confirmation()
        challenges = self.env["proof.challenge"]
        for record in self:
            partner = record._get_confirmation_partner()
            if not partner:
                continue
            record = record.with_context(lang=partner.lang or record.env.lang)
            challenges._issue_confirmation(
                record,
                record._get_confirmation_purpose(),
                record._get_confirmation_facts(),
                partner,
                summary=record._get_confirmation_summary(),
                lifetime=record._get_confirmation_lifetime(),
                remind_after=record._get_confirmation_reminder_delay(),
            )

    def _withdraw_confirmation(self) -> None:
        if not self:
            return
        self.env["proof.challenge"]._with_proof_privilege().search(
            [
                ("res_model", "=", self._name),
                ("res_id", "in", self.ids),
                ("purpose", "=", self._get_confirmation_purpose()),
                ("state", "=", "issued"),
            ]
        )._withdraw()

    def _is_confirmation_current(self) -> bool:
        """Whether the contact confirmed the record as it stands now."""
        self.check_singleton()
        challenge = self._get_confirmation_challenges().get(self.id)
        return bool(
            challenge
            and challenge.state == "redeemed"
            and challenge.verdict == "confirmed"
            and challenge.digest
            == challenge._get_digest(
                self._get_confirmation_purpose(), self, self._get_confirmation_facts()
            )
        )

    def action_issue_confirmation_code(self) -> dict[str, Any]:
        """With the contact at the counter: send them a code, and return what the
        dialog needs to take it."""
        self.check_singleton()
        partner = self._get_confirmation_partner()
        if not partner or self.confirmation_state == "confirmed":
            raise UserError(
                self.env._(
                    "%s does not wait for its contact to confirm it.",
                    self.display_name,
                )
            )
        return self.env["proof.challenge"]._issue(
            self,
            self._get_confirmation_purpose(),
            self._get_confirmation_facts(),
            self.env["proof.method"].search([("mode", "=", "submit")]),
            summary=self._get_confirmation_summary(),
            partner=partner,
        )

    def action_prove_confirmation_code(self, proof: dict[str, Any]) -> None:
        self.check_singleton()
        purpose = self._get_confirmation_purpose()
        evidence = self.env["proof.challenge"]._redeem(
            proof.get("token"),
            proof.get("method"),
            proof.get("payload") or {},
            self,
            purpose,
            self._get_confirmation_facts(),
            verdict="confirmed",
        )
        self._withdraw_confirmation()
        self._on_confirmation_answered(evidence)

    def _on_confirmation_answered(self, evidence: models.BaseModel) -> None:
        """The contact answered: ``evidence.verdict`` says how."""

    def _on_confirmation_expired(self) -> None:
        """The contact did not answer in time."""

    def _on_confirmation_comment(self, evidence: models.BaseModel, text: str) -> None:
        """The contact who answered ``evidence`` added ``text``, on a channel
        that takes their words after their answer."""
