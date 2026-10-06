from odoo import fields, models
from odoo.tools import frozendict


class HrRecruitmentReport(models.Model):
    _inherit = "hr.recruitment.report"
    _depends = frozendict(
        {
            "hr.applicant": ["ref_user_id"],
        }
    )

    has_referrer = fields.Integer(
        readonly=True,
        aggregator="sum",
    )
    referral_hired = fields.Integer(
        string="# Hired by Referral",
        readonly=True,
        aggregator="sum",
    )

    def _query(self, fields="", from_clause=""):
        fields += """
            , CASE WHEN a.ref_user_id IS NOT NULL THEN 1 ELSE 0 END as has_referrer,
            CASE WHEN a.date_closed IS NOT NULL AND a.ref_user_id IS NOT NULL THEN 1 ELSE 0 END as referral_hired
            """

        return super()._query(fields, from_clause)
