import json
import secrets
from datetime import timedelta
from hashlib import sha256
from typing import Any

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.http import request

CHALLENGE_LIFETIME = timedelta(minutes=5)
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
    user_id = fields.Many2one(
        comodel_name="res.users",
        index=True,
        readonly=True,
        required=True,
        ondelete="cascade",
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
    state = fields.Selection(
        selection=[
            ("issued", "Issued"),
            ("redeemed", "Redeemed"),
        ],
        default="issued",
        readonly=True,
        required=True,
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
    ) -> dict[str, Any]:
        """Ask the current user to prove they vouch for ``facts`` about ``record``,
        and return what the client needs to ask them: the only place the
        challenge's token is ever given out, since the challenge keeps its hash.

        ``facts`` must be JSON-serialisable and carry every figure the user agrees
        to; redeeming recomputes the digest from the facts as they are then, so a
        figure that moved in between refuses the proof. ``summary`` is what the
        user is shown, as label/value pairs.
        """
        record.check_singleton()
        user = self.env.user
        methods = methods.filtered(lambda method: method._is_enrolled(user))
        if not methods:
            raise UserError(
                self.env._(
                    "You have no way set up to prove this is you. Ask an "
                    "administrator which proof methods apply, and set one up."
                )
            )
        token = secrets.token_urlsafe(32)
        challenge = self._with_proof_privilege().create(
            {
                "token_hash": self._get_token_hash(token),
                "user_id": user.id,
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
    ) -> models.BaseModel:
        """Accept the current user's answer to a challenge and record it.

        Returns the ``proof.evidence`` row. Raises UserError when the challenge is
        unknown, used, expired, someone else's, issued for another act, answered
        with a method it did not offer, when the facts moved since it was issued,
        or when the method refuses the proof.
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
        challenge.state = "redeemed"
        evidence = challenge.env["proof.evidence"].create(
            challenge._prepare_evidence_vals(method, accepted)
        )
        return self.env["proof.evidence"].browse(evidence.id)

    def _get_client_params(self, token: str) -> dict[str, Any]:
        self.check_singleton()
        return {
            "token": token,
            "expires": fields.Datetime.to_string(self.date_expire),
            "summary": self.summary or [],
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
        self, method: models.BaseModel, accepted: dict[str, Any]
    ) -> dict[str, Any]:
        self.check_singleton()
        httprequest = request.httprequest if request else None
        return {
            "user_id": self.user_id.id,
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
        stale = self.search(
            [("date_expire", "<", fields.Datetime.now() - CHALLENGE_RETENTION)],
            limit=GC_UNLINK_LIMIT,
        )
        stale.unlink()
        return len(stale), len(stale) == GC_UNLINK_LIMIT
