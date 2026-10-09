from odoo import api, fields, models
from odoo.exceptions import ValidationError

PROOF_VERDICTS = {
    "none": (),
    "approve": ("approve",),
    "approve_refuse": ("approve", "refuse"),
}


class ApprovalCategory(models.Model):
    _inherit = "approval.category"

    proof_verdicts = fields.Selection(
        selection=[
            ("none", "No proof"),
            ("approve", "Approvals"),
            ("approve_refuse", "Approvals and refusals"),
        ],
        string="Proof of Identity For",
        default="none",
        required=True,
        help="Which decisions count only once the approver proves it is them, "
        "with a proof covering the request's figures. A refusal that says a "
        "handover did not happen accuses the other party: prove it too.",
    )
    proof_method_ids = fields.Many2many(
        comodel_name="proof.method",
        string="Accepted Proof Methods",
    )
    allow_delegation = fields.Boolean(
        default=True,
        help="Whether an approver may have someone else decide in their place. "
        "A handover is acknowledged by the people who handed and received: "
        "turn it off there.",
    )

    @api.constrains("proof_verdicts", "proof_method_ids", "consent_approval_hours")
    def _check_proof_settings(self) -> None:
        for category in self.filtered(lambda c: c.proof_verdicts != "none"):
            if not category.proof_method_ids:
                raise ValidationError(
                    self.env._(
                        "%(category)s asks for a proof of identity: choose the "
                        "proof methods it accepts.",
                        category=category.display_name,
                    )
                )
            if category.consent_approval_hours:
                raise ValidationError(
                    self.env._(
                        "%(category)s asks for a proof of identity, so its "
                        "requests cannot be approved by consent.",
                        category=category.display_name,
                    )
                )

    def _is_proof_required(self, decision: str) -> bool:
        self.check_singleton()
        return decision in PROOF_VERDICTS[self.proof_verdicts or "none"]
