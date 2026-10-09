import json
import secrets
from datetime import timedelta
from hashlib import sha256
from typing import Any

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.http import request

from .proof_method import MODES, VERDICTS

CHALLENGE_LIFETIME = timedelta(minutes=5)
CONFIRMATION_LIFETIME = timedelta(days=3)
CHALLENGE_RETENTION = timedelta(days=1)
GC_UNLINK_LIMIT = 10000


class ProofChallenge(models.Model):
    _name = "proof.challenge"
    _description = "Proof Challenge"
    _order = "id desc"

    token_hash = fields.Char(
        copy=False,
        readonly=True,
        required=True,
    )
    kind = fields.Selection(
        selection=MODES,
        default="submit",
        readonly=True,
        required=True,
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        index=True,
        readonly=True,
        required=True,
        ondelete="cascade",
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Contact",
        readonly=True,
        ondelete="cascade",
        help="The contact asked to prove it is them, when it is not the user.",
    )
    purpose = fields.Char(
        readonly=True,
        required=True,
    )
    res_model = fields.Char(
        readonly=True,
        required=True,
    )
    res_id = fields.Many2oneReference(
        model_field="res_model",
        readonly=True,
        required=True,
    )
    facts = fields.Json(
        readonly=True,
    )
    summary = fields.Json(
        readonly=True,
    )
    digest = fields.Char(
        readonly=True,
        required=True,
    )
    method_ids = fields.Many2many(
        comodel_name="proof.method",
        string="Methods",
        readonly=True,
    )
    date_expire = fields.Datetime(
        readonly=True,
        required=True,
    )
    code_hash = fields.Char(
        copy=False,
        readonly=True,
        help="HMAC of the one-time code sent to the signer, under the database secret.",
    )
    code_attempts = fields.Integer(
        default=0,
        copy=False,
        readonly=True,
    )
    code_sent_to = fields.Char(
        string="Code Sent To",
        copy=False,
        readonly=True,
        help="Where the code went, masked.",
    )
    date_remind = fields.Datetime(
        string="Remind On",
        readonly=True,
        help="When a contact who has not answered yet is reminded.",
    )
    state = fields.Selection(
        selection=[
            ("issued", "Issued"),
            ("redeemed", "Redeemed"),
            ("withdrawn", "Withdrawn"),
            ("expired", "Expired"),
        ],
        default="issued",
        readonly=True,
        required=True,
    )
    verdict = fields.Selection(
        selection=VERDICTS,
        readonly=True,
    )
    evidence_id = fields.Many2one(
        comodel_name="proof.evidence",
        readonly=True,
        ondelete="restrict",
    )
    delivery_ids = fields.One2many(
        comodel_name="proof.delivery",
        inverse_name="challenge_id",
        readonly=True,
    )

    _token_hash_uniq = models.Constraint(
        "unique(token_hash)",
        "A proof challenge token is unique.",
    )

    @api.model
    def _issue(
        self,
        record: models.BaseModel,
        purpose: str,
        facts: dict[str, Any],
        methods: models.BaseModel,
        summary: list[list[str]] | None = None,
        partner: models.BaseModel | None = None,
    ) -> dict[str, Any]:
        """Ask the current user to prove they vouch for ``facts`` about ``record``,
        and return what the client needs to ask them: the only place the
        challenge's token is ever given out, since the challenge keeps its hash.

        ``facts`` must be JSON-serialisable and carry every figure the user agrees
        to; redeeming recomputes the digest from the facts as they are then, so a
        figure that moved in between refuses the proof. ``summary`` is what the
        user is shown, as label/value pairs. With ``partner``, the contact is the
        one who proves, through the current user, who enters their answer.
        """
        record.check_singleton()
        user = self.env.user
        methods = methods.filtered(lambda method: method.mode == "submit")
        if partner:
            partner.check_singleton()
            methods = methods.filtered(
                lambda method: method._is_enrolled_contact(partner)
            )
        else:
            methods = methods.filtered(lambda method: method._is_enrolled(user))
        if not methods:
            raise UserError(
                self.env._(
                    "%(contact)s has no way set up to prove it is them.",
                    contact=partner.display_name,
                )
                if partner
                else self.env._(
                    "You have no way set up to prove this is you. Ask an "
                    "administrator which proof methods apply, and set one up."
                )
            )
        token = secrets.token_urlsafe(32)
        challenge = self._with_proof_privilege().create(
            {
                "token_hash": self._get_token_hash(token),
                "user_id": user.id,
                "partner_id": partner.id if partner else False,
                "purpose": purpose,
                "res_model": record._name,
                "res_id": record.id,
                "facts": facts,
                "summary": summary or [],
                "digest": self._get_digest(purpose, record, facts),
                "method_ids": methods.ids,
                "date_expire": fields.Datetime.now() + CHALLENGE_LIFETIME,
            }
        )
        return challenge._get_client_params(token)

    @api.model
    def _redeem(
        self,
        token: str,
        method_code: str,
        payload: dict[str, Any],
        record: models.BaseModel,
        purpose: str,
        facts: dict[str, Any],
        verdict: str | None = None,
    ) -> models.BaseModel:
        """Accept the current user's answer to a challenge and record it.

        Returns the ``proof.evidence`` row. Raises UserError when the challenge is
        unknown, used, expired, someone else's, issued for another act, answered
        with a method it did not offer, when the facts moved since it was issued,
        or when the method refuses the proof. ``verdict`` is what a contact
        answered to what they were asked to confirm, when they were.
        """
        record.check_singleton()
        challenge = self._with_proof_privilege().search(
            [("token_hash", "=", self._get_token_hash(token or ""))], limit=1
        )
        challenge._check_redeemable(record, purpose, facts)
        method = challenge.method_ids.filtered(
            lambda method: method.code == method_code
        )
        if not method:
            raise UserError(
                self.env._("This proof method was not offered for this request.")
            )
        accepted = method._accept_proof(challenge, payload or {})
        evidence = challenge._record_answer(method, accepted, verdict)
        return self.env["proof.evidence"].browse(evidence.id)

    @api.model
    def _issue_confirmation(
        self,
        record: models.BaseModel,
        purpose: str,
        facts: dict[str, Any],
        partner: models.BaseModel,
        summary: list[list[str]] | None = None,
        lifetime: timedelta = CONFIRMATION_LIFETIME,
        remind_after: timedelta | None = None,
    ) -> ProofChallenge:
        """Ask ``partner`` to confirm ``facts`` about ``record`` on every channel
        of theirs a confirmation method reaches; they answer there, until
        ``lifetime`` runs out. A challenge no channel reached is still issued,
        with no message out, so the record shows its contact was unreachable.
        """
        record.check_singleton()
        partner.check_singleton()
        methods = (
            self.env["proof.method"]
            .search([("mode", "=", "confirm")])
            .filtered(lambda method: method._is_enrolled_contact(partner))
        )
        now = fields.Datetime.now()
        challenge = self._with_proof_privilege().create(
            {
                "kind": "confirm",
                # never handed out: the contact answers on the messages sent
                "token_hash": self._get_token_hash(secrets.token_urlsafe(32)),
                "user_id": self.env.user.id,
                "partner_id": partner.id,
                "purpose": purpose,
                "res_model": record._name,
                "res_id": record.id,
                "facts": facts,
                "summary": summary or [],
                "digest": self._get_digest(purpose, record, facts),
                "method_ids": methods.ids,
                "date_expire": now + lifetime,
                "date_remind": now + remind_after if remind_after else False,
            }
        )
        challenge._deliver()
        return self.browse(challenge.id)

    def _deliver(self, reminder: bool = False) -> None:
        for challenge in self:
            for method in challenge.method_ids:
                method._deliver_confirmation(challenge, reminder=reminder)

    def _record_answer(
        self,
        method: models.BaseModel,
        accepted: dict[str, Any],
        verdict: str | None = None,
        signer_request: bool = True,
    ) -> models.BaseModel:
        self.check_singleton()
        evidence = self.env["proof.evidence"].create(
            self._prepare_evidence_vals(
                method, accepted, verdict=verdict, signer_request=signer_request
            )
        )
        self.write(
            {"state": "redeemed", "verdict": verdict, "evidence_id": evidence.id}
        )
        return evidence

    def _withdraw(self) -> None:
        """Take back what was asked: its messages can no longer be answered."""
        challenges = self._with_proof_privilege().browse(self.ids)
        challenges.filtered(lambda c: c.state == "issued").state = "withdrawn"
        challenges._withdraw_deliveries()

    def _withdraw_deliveries(self) -> None:
        for delivery in self.delivery_ids.filtered(lambda d: d.state == "sent"):
            delivery.state = "withdrawn"
            delivery.method_id._withdraw_delivery(delivery)

    def _get_record_links(self) -> list[tuple[str, str]]:
        """The links the record sends along with what its contact confirms, in
        the contact's language."""
        self.check_singleton()
        record = (
            self.env[self.res_model]
            .with_context(lang=self.partner_id.lang or self.env.lang)
            .browse(self.res_id)
            .exists()
        )
        if not record or not hasattr(record, "_get_confirmation_links"):
            return []
        return record._get_confirmation_links()

    def _notify_record(self, hook: str, *args: Any) -> None:
        self.check_singleton()
        # the contact answers from outside, as no user of ours and inside no
        # company: the record hears it as the user who asked them
        context = dict(self.env.context)
        context.pop("allowed_company_ids", None)
        asker_env = self.env(user=self.user_id.id, context=context)
        record = asker_env[self.res_model].browse(self.res_id).exists()
        # a record outside the confirmation mixin asked its contact directly
        # and follows the answer from the challenge
        if record and hasattr(record, hook):
            getattr(record, hook)(*args)

    @api.model
    def _cron_follow_up_confirmations(self) -> None:
        challenges = self._with_proof_privilege()
        now = fields.Datetime.now()
        expired = challenges.search(
            [
                ("kind", "=", "confirm"),
                ("state", "=", "issued"),
                ("date_expire", "<=", now),
            ]
        )
        for challenge in expired:
            challenge.state = "expired"
            challenge._withdraw_deliveries()
            challenge._notify_record("_on_confirmation_expired")
        due = challenges.search(
            [
                ("kind", "=", "confirm"),
                ("state", "=", "issued"),
                ("date_remind", "<=", now),
            ]
        )
        due.date_remind = False
        due._deliver(reminder=True)

    def _get_client_params(self, token: str) -> dict[str, Any]:
        self.check_singleton()
        return {
            "token": token,
            "expires": fields.Datetime.to_string(self.date_expire),
            "summary": self.summary or [],
            "signer": self.partner_id.display_name or None,
            "methods": [
                {
                    "code": method.code,
                    "name": method.name,
                    "options": method._get_proof_options(self),
                }
                for method in self.method_ids
            ],
        }

    def _check_redeemable(
        self, record: models.BaseModel, purpose: str, facts: dict[str, Any]
    ) -> None:
        if (
            not self
            or self.kind != "submit"
            or self.state != "issued"
            or self.date_expire < fields.Datetime.now()
        ):
            raise UserError(
                self.env._(
                    "This proof request expired or was already used. Start again."
                )
            )
        if self.user_id != self.env.user:
            raise UserError(
                self.env._("This proof request was issued to someone else.")
            )
        if (self.purpose, self.res_model, self.res_id) != (
            purpose,
            record._name,
            record.id,
        ):
            raise UserError(
                self.env._("This proof request was issued for another act.")
            )
        if self._get_digest(purpose, record, facts) != self.digest:
            raise UserError(
                self.env._(
                    "The record changed since you were asked to prove it. Review it "
                    "and start again."
                )
            )

    def _prepare_evidence_vals(
        self,
        method: models.BaseModel,
        accepted: dict[str, Any],
        verdict: str | None = None,
        signer_request: bool = True,
    ) -> dict[str, Any]:
        self.check_singleton()
        httprequest = request.httprequest if request and signer_request else None
        return {
            "user_id": self.user_id.id,
            "partner_id": self.partner_id.id,
            "purpose": self.purpose,
            "res_model": self.res_model,
            "res_id": self.res_id,
            "facts": self.facts,
            "summary": self.summary,
            "digest": self.digest,
            "nonce": self.token_hash,
            "method_id": method.id,
            "method_code": method.code,
            "strength": method.strength,
            "payload": accepted,
            "verdict": verdict,
            "date": fields.Datetime.now(),
            "ip": httprequest.remote_addr if httprequest else False,
            "user_agent": httprequest.user_agent.string[:512] if httprequest else False,
        }

    @api.model
    def _get_token_hash(self, token: str) -> str:
        return sha256(token.encode()).hexdigest()

    @api.model
    def _get_digest(
        self, purpose: str, record: models.BaseModel, facts: dict[str, Any]
    ) -> str:
        text = json.dumps(
            {
                "purpose": purpose,
                "res_model": record._name,
                "res_id": record.id,
                "facts": facts,
            },
            sort_keys=True,
            ensure_ascii=True,
            separators=(",", ":"),
        )
        return sha256(text.encode()).hexdigest()

    @api.model
    def _with_proof_privilege(self) -> ProofChallenge:
        return self.with_privilege(
            "proof.privilege_record_proof",
            reason="a user proves who they are for an act they vouch for",
        )

    @api.autovacuum
    def _gc_challenges(self) -> tuple[int, bool]:
        # a confirmation stays: its record reads its answer from it
        stale = self.search(
            [
                ("kind", "=", "submit"),
                ("date_expire", "<", fields.Datetime.now() - CHALLENGE_RETENTION),
            ],
            limit=GC_UNLINK_LIMIT,
        )
        stale.unlink()
        return len(stale), len(stale) == GC_UNLINK_LIMIT
