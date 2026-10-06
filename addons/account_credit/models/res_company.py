from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    credit_config_id = fields.Many2one(
        comodel_name="credit.config",
        compute="_compute_credit_config_id",
        search="_search_credit_config_id",
    )
    credit_folder_id = fields.Many2one(
        related="credit_config_id.credit_folder_id",
        readonly=False,
    )

    def _search_credit_config_id(self, operator, value):
        return self._search_config_link("credit.config", operator, value)

    def _compute_credit_config_id(self) -> None:
        self._compute_config_link("credit_config_id")
