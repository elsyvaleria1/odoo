from typing import Any

from odoo import models
from odoo.exceptions import UserError
from odoo.tools import format_amount
from odoo.tools.authority_keys import declare_authority_keys

PROOF_PURPOSE = "approval.decision"
SUMMARY_RECORDS = 5

# set only in-process, by the entry points that take the proof as an argument
declare_authority_keys("approval_proof", "approval_proof", "approval_proof_evidence_id")


class ApprovalRequest(models.Model):
    _inherit = "approval.request"

    def action_issue_decision_proof(self, decision: str) -> dict[str, Any] | None:
        """The proof the current user must give to decide this request, or None
        when its category needs none for that decision."""
        self.check_singleton()
        self.check_access("read")
        if decision not in ("approve", "refuse"):
            raise UserError(self.env._("Unknown decision: %s", decision))
        if not self.category_id._is_proof_required(decision):
            return None
        if self.state != "pending" or not self._get_current_pending_approver():
            self._raise_not_assigned_approver()
        return self.env["proof.challenge"]._issue(
            self,
            PROOF_PURPOSE,
            self._get_decision_proof_facts(decision),
            self.category_id.proof_method_ids,
            summary=self._get_decision_proof_summary(decision),
        )

    def action_approve_with_proof(self, proof: dict[str, Any]) -> dict[str, Any] | None:
        self.check_singleton()
        return self.with_context(approval_proof=proof).action_approve()

    def _apply_decision(
        self,
        decision: str,
        approver: models.BaseModel | None = None,
        steps: models.BaseModel | None = None,
    ) -> None:
        self.check_singleton()
        if not self.category_id._is_proof_required(decision):
            return super()._apply_decision(decision, approver, steps)
        proof = self.env.context.get("approval_proof")
        if not isinstance(proof, dict):
            raise UserError(
                self.env._(
                    "%(request)s needs a proof that it is you before your decision "
                    "counts. Decide it from the request, or from your approval "
                    "activity, one request at a time.",
                    request=self.display_name,
                )
            )
        evidence = self.env["proof.challenge"]._redeem(
            proof.get("token"),
            proof.get("method"),
            proof.get("payload") or {},
            self,
            PROOF_PURPOSE,
            self._get_decision_proof_facts(decision),
        )
        proven = self.with_context(
            approval_proof=None, approval_proof_evidence_id=evidence.id
        )
        return super(ApprovalRequest, proven)._apply_decision(decision, approver, steps)

    def _get_decision_proof_facts(self, decision: str) -> dict[str, Any]:
        """What a proven decision vouches for: the request's figures, the
        decision, the deciding row and the source document's protected fields."""
        self.check_singleton()
        facts = {
            "decision": decision,
            "request": self.id,
            "approver": self._get_current_pending_approver()[:1].id or None,
            "category": self.category_id.id,
            "amount": repr(self.amount) if self.amount else None,
            "currency": self.currency_id.name or None,
        }
        document = self.get_source_document()
        if document and len(document) == 1:
            facts["document"] = {
                "model": document._name,
                "id": document.id,
                "fields": {
                    name: self._get_proof_fact_value(document, name)
                    for name in sorted(self._get_proof_document_fields(document))
                },
            }
        return facts

    def _get_decision_proof_summary(self, decision: str) -> list[list[str]]:
        self.check_singleton()
        summary = [
            [
                self.env._("Decision"),
                self.env._("Approve")
                if decision == "approve"
                else self.env._("Refuse"),
            ],
            [self.env._("Request"), self.display_name],
        ]
        if self.amount:
            summary.append(
                [
                    self.env._("Amount"),
                    format_amount(self.env, self.amount, self.currency_id),
                ]
            )
        document = self.get_source_document()
        if document and len(document) == 1:
            summary.append([self.env._("Document"), document.display_name])
            for name in self._get_proof_document_fields(document):
                field = document._fields[name]
                summary.append(
                    [
                        field._description_string(self.env),
                        self._get_proof_display_value(document, name),
                    ]
                )
        return summary

    def _get_proof_display_value(self, record: models.BaseModel, name: str) -> str:
        field = record._fields[name]
        value = record[name]
        if field.type in ("one2many", "many2many"):
            shown = ", ".join(value[:SUMMARY_RECORDS].mapped("display_name"))
            if len(value) > SUMMARY_RECORDS:
                return self.env._(
                    "%(shown)s and %(more)s more",
                    shown=shown,
                    more=len(value) - SUMMARY_RECORDS,
                )
            return shown
        if field.type == "monetary":
            currency_field = field.get_currency_field(record)
            currency = record[currency_field] if currency_field else self.currency_id
            return format_amount(self.env, value, currency)
        return field.convert_to_display_name(value, record) or ""

    def _get_proof_document_fields(self, document: models.BaseModel) -> list[str]:
        protected = getattr(document, "_get_fields_approval_protected", None)
        return [
            name
            for name in (protected() if protected else [])
            if name in document._fields
        ]

    def _get_proof_fact_value(self, record: models.BaseModel, name: str) -> Any:
        field = record._fields[name]
        value = record[name]
        if field.type == "many2one":
            return value.id or None
        if field.type in ("one2many", "many2many"):
            return sorted(value.ids)
        if field.type in ("date", "datetime"):
            return field.to_string(value) if value else None
        if field.type in ("float", "monetary"):
            return repr(value)
        if field.type == "binary" or value is False:
            return None
        return value
