from odoo import fields, models


class HrReferralOnboarding(models.Model):
    _name = "hr.referral.onboarding"
    _description = "Welcome Onboarding in Referral App"
    _order = "sequence"
    _rec_name = "text"

    sequence = fields.Integer()
    text = fields.Text(
        translate=True,
        required=True,
    )
    image = fields.Binary(required=True)
    company_id = fields.Many2one(comodel_name="res.company")

    def action_relaunch_onboarding(self) -> None:
        self.env["res.users"].sudo().search(
            [
                ("company_id", "in", self.env.companies.ids),
                ("share", "=", False),
            ]
        ).write({"hr_referral_onboarding_page": False})
