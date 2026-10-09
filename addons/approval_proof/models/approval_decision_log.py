from odoo import api, fields, models


class ApprovalDecisionLog(models.Model):
    _inherit = "approval.decision.log"

    evidence_id = fields.Many2one(
        comodel_name="proof.evidence",
        string="Proof",
        index="btree_not_null",
        readonly=True,
        ondelete="restrict",
    )

    @api.model_create_multi
    def create(self, vals_list):
        evidence_id = self.env.context.get("approval_proof_evidence_id")
        if evidence_id:
            for vals in vals_list:
                # the deciding user's own rows; a row flipped by their refusal
                # or decided as someone else's delegate names a principal
                if (
                    vals.get("verdict") in ("approved", "refused")
                    and vals.get("approver_id")
                    and not vals.get("principal_id")
                ):
                    vals["evidence_id"] = evidence_id
        return super().create(vals_list)
