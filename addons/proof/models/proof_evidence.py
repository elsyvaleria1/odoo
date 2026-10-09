import json
from hashlib import sha256
from itertools import batched
from typing import Any

import psycopg

from odoo import api, fields, models
from odoo.exceptions import ConcurrencyError, UserError
from odoo.tools import frozendict

from .proof_method import STRENGTHS, VERDICTS

HASH_VERSION = 3
HASHED_FIELDS_V1 = (
    "sequence",
    "prev_hash",
    "hash_version",
    "user_id",
    "purpose",
    "res_model",
    "res_id",
    "facts",
    "summary",
    "digest",
    "nonce",
    "method_code",
    "strength",
    "payload",
    "date",
    "ip",
    "user_agent",
)
# a row is rehashed with the fields of the version it was recorded under
HASHED_FIELDS = {
    1: HASHED_FIELDS_V1,
    2: (*HASHED_FIELDS_V1, "partner_id"),
    3: (*HASHED_FIELDS_V1, "partner_id", "verdict"),
}


class ProofEvidence(models.Model):
    _name = "proof.evidence"
    _description = "Proof Evidence"
    _order = "sequence desc"
    _rec_name = "sequence"
    _access_anchors = frozendict({"owner": "user_id", "company": ""})

    sequence = fields.Integer(
        string="Chain Position",
        readonly=True,
        required=True,
    )
    prev_hash = fields.Char(
        string="Previous Hash",
        readonly=True,
    )
    hash = fields.Char(
        readonly=True,
        required=True,
    )
    hash_version = fields.Integer(
        readonly=True,
        required=True,
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Proven By",
        index=True,
        readonly=True,
        required=True,
        ondelete="restrict",
        help="The user who proved it is them, or who asked the contact for the "
        "proof and entered it.",
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Proven By Contact",
        index="btree_not_null",
        readonly=True,
        ondelete="restrict",
        help="The contact with no user account who proved it is them, through "
        "the user who asked them.",
    )
    purpose = fields.Char(
        readonly=True,
        required=True,
    )
    res_model = fields.Char(
        string="Record Model",
        index=True,
        readonly=True,
        required=True,
    )
    res_id = fields.Many2oneReference(
        model_field="res_model",
        string="Record",
        index=True,
        readonly=True,
        required=True,
    )
    facts = fields.Json(
        readonly=True,
        help="The figures of the record the user vouched for, as the digest covers them.",
    )
    summary = fields.Json(
        readonly=True,
        help="What the user was shown when asked for the proof.",
    )
    digest = fields.Char(
        readonly=True,
        required=True,
    )
    nonce = fields.Char(
        readonly=True,
        required=True,
    )
    method_id = fields.Many2one(
        comodel_name="proof.method",
        string="Method",
        readonly=True,
        required=True,
        ondelete="restrict",
    )
    method_code = fields.Char(
        readonly=True,
        required=True,
    )
    strength = fields.Selection(
        selection=STRENGTHS,
        readonly=True,
        required=True,
    )
    payload = fields.Json(
        readonly=True,
        help="The proof as the method accepted it, kept so it can be checked again.",
    )
    verdict = fields.Selection(
        selection=VERDICTS,
        readonly=True,
        help="What the contact answered to what they were asked to confirm, when "
        "they were asked to confirm it on their own channel or at the counter.",
    )
    date = fields.Datetime(
        readonly=True,
        required=True,
    )
    ip = fields.Char(
        string="IP Address",
        readonly=True,
    )
    user_agent = fields.Char(
        readonly=True,
    )

    _sequence_uniq = models.Constraint(
        "unique(sequence)",
        "Two proofs cannot hold the same chain position.",
    )
    _nonce_uniq = models.Constraint(
        "unique(nonce)",
        "A proof challenge is answered once.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        head = self._get_chain_head()
        sequence, prev_hash = head.sequence or 0, head.hash or ""
        for vals in vals_list:
            sequence += 1
            vals.update(
                sequence=sequence, prev_hash=prev_hash, hash_version=HASH_VERSION
            )
            vals["hash"] = prev_hash = self._get_chained_hash(vals)
        # what is pending is written first: a conflict of its own is not this
        # chain's, and must not read as a concurrent proof
        self.env.flush_all()
        try:
            with self.env.cr.savepoint():
                return super().create(vals_list)
        except psycopg.errors.UniqueViolation:
            # a concurrent proof took the position this snapshot computed:
            # replaying on a snapshot that sees it chains after it
            raise ConcurrencyError(
                "proof.evidence: a concurrent proof took this chain position"
            ) from None

    def write(self, vals):
        if not self:
            return True
        raise UserError(self.env._("Recorded proof evidence cannot be changed."))

    @api.ondelete(at_uninstall=False)
    def _unlink_never(self) -> None:
        raise UserError(self.env._("Recorded proof evidence cannot be deleted."))

    def action_check_chain(self) -> dict[str, Any]:
        error = self._get_chain_error()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "danger" if error else "success",
                "title": self.env._("Proof evidence chain"),
                "message": error or self.env._("Every recorded proof is intact."),
                "sticky": bool(error),
            },
        }

    @api.model
    def _get_chain_head(self) -> ProofEvidence:
        return self.search([], order="sequence desc", limit=1)

    def _get_chained_hash(self, vals: dict[str, Any]) -> str:
        payload = {
            name: self._normalize_hashed(name, vals.get(name))
            for name in HASHED_FIELDS[vals["hash_version"]]
        }
        text = json.dumps(
            payload, sort_keys=True, ensure_ascii=True, separators=(",", ":")
        )
        return sha256((vals["prev_hash"] + text).encode()).hexdigest()

    def _normalize_hashed(self, name: str, value: Any) -> Any:
        if isinstance(value, models.BaseModel):
            return value.id or None
        if name == "date" and value:
            return fields.Datetime.to_string(fields.Datetime.to_datetime(value))
        if (
            value is None
            or value is False
            or (isinstance(value, str | dict | list) and not value)
        ):
            return None
        return value

    def _get_hash_vals(self) -> dict[str, Any]:
        self.check_singleton()
        return {name: self[name] for name in HASHED_FIELDS[self.hash_version]}

    def _get_chain_error(self) -> str | None:
        """Why the whole chain no longer vouches for its proofs, or None: the first
        position missing, the first row not linked to its predecessor, or the
        first row whose content no longer matches its hash."""
        expected, prev_hash = 1, ""
        for ids in batched(self.search([], order="sequence").ids, 1000, strict=False):
            for evidence in self.browse(ids):
                if evidence.sequence != expected:
                    return self.env._(
                        "Proof %(position)s is missing from the chain.",
                        position=expected,
                    )
                if (evidence.prev_hash or "") != prev_hash:
                    return self.env._(
                        "Proof %(position)s is not linked to the proof before it.",
                        position=expected,
                    )
                if evidence.hash_version not in HASHED_FIELDS:
                    return self.env._(
                        "Proof %(position)s claims a hash version this database "
                        "does not know.",
                        position=expected,
                    )
                if self._get_chained_hash(evidence._get_hash_vals()) != evidence.hash:
                    return self.env._(
                        "Proof %(position)s was changed after it was recorded.",
                        position=expected,
                    )
                expected, prev_hash = expected + 1, evidence.hash
            self.invalidate_model()
        return None
