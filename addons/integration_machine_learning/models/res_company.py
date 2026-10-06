from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    ml_config_id = fields.Many2one(
        comodel_name="integration.ml.config",
        compute="_compute_ml_config_id",
        search="_search_ml_config_id",
    )

    ml_monthly_budget = fields.Float(
        related="ml_config_id.ml_monthly_budget",
        readonly=False,
    )
    ml_spend_this_month = fields.Float(
        related="ml_config_id.ml_spend_this_month",
    )

    def _search_ml_config_id(self, operator, value):
        return self._search_config_link("integration.ml.config", operator, value)

    def _compute_ml_config_id(self) -> None:
        self._compute_config_link("ml_config_id")

    def _ml_spend_this_month(self):
        self.check_singleton()
        month_start = fields.Datetime.now().replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        [[spent]] = (
            self.env["integration.exchange"]
            .sudo()
            ._read_group(
                [
                    ("company_id", "=", self.id),
                    ("timestamp", ">=", month_start),
                    ("ml_cost", "!=", 0),
                ],
                aggregates=["ml_cost:sum"],
            )
        )
        return spent or 0.0
