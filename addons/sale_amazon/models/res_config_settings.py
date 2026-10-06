from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    has_amazon_account = fields.Boolean(compute="_compute_has_amazon_account")

    @api.depends("company_id")
    def _compute_has_amazon_account(self) -> None:
        self.has_amazon_account = self.env["amazon.account"].search_count(
            [*self.env["amazon.account"]._check_company_domain(self.env.company)],
            limit=1,
        )
