from odoo import fields, models


class ProofEvidence(models.Model):
    _inherit = "proof.evidence"

    approval_decision_log_ids = fields.One2many(
        comodel_name="approval.decision.log",
        inverse_name="evidence_id",
        readonly=True,
    )
