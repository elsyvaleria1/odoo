from odoo import fields, models


class IntegrationMlConfig(models.Model):
    _name = "integration.ml.config"
    _description = "A company's machine learning configuration"
    _inherit = ["mixin.company.config"]

    ml_monthly_budget = fields.Float(
        string="Monthly ML Budget (USD)",
        groups="base.group_system",
        help="Once this company's machine learning exchanges of the current month "
        "have cost this much at the model rows' prices, no further call to a "
        "machine learning vendor is made until the month turns. Zero sets no cap.",
    )
    ml_spend_this_month = fields.Float(
        string="ML Spend This Month (USD)",
        compute="_compute_ml_spend_this_month",
        groups="base.group_system",
        help="What this company's machine learning exchanges since the first of "
        "the month cost, as recorded on their exchange rows.",
    )

    def _compute_ml_spend_this_month(self) -> None:
        for company in self:
            company.ml_spend_this_month = company.company_id._ml_spend_this_month()
