from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    hr_referral_background = fields.Image(
        related="company_id.hr_referral_background",
        readonly=False,
    )

    def restore_default_referral_background(self) -> None:
        self.hr_referral_background = self.env[
            "res.company"
        ]._get_default_referral_background()
        self.env["ir.config_parameter"].sudo().set_param(
            "hr_referral.show_grass", "true"
        )
