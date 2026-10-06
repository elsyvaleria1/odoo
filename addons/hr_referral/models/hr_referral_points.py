from odoo import api, fields, models
from odoo.tools import frozendict


class HrReferralPoints(models.Model):
    _name = "hr.referral.points"
    _description = "Points line for referrals"
    _access_anchors = frozendict(
        {
            "owner": "ref_user_id",
        }
    )

    applicant_id = fields.Many2one(
        comodel_name="hr.applicant",
        index=True,
    )
    applicant_name = fields.Char(related="applicant_id.partner_name")
    hr_referral_reward_id = fields.Many2one(
        comodel_name="hr.referral.reward",
        string="Reward",
    )
    ref_user_id = fields.Many2one(
        comodel_name="res.users",
        string="User",
        index=True,
        required=True,
    )
    points = fields.Integer()
    stage_id = fields.Many2one(comodel_name="hr.recruitment.stage")
    sequence_stage = fields.Integer(
        related="stage_id.sequence",
        string="Sequence of stage",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        required=True,
    )

    @api.depends("points")
    def _compute_display_name(self):
        for record in self:
            record.display_name = str(record.points)
