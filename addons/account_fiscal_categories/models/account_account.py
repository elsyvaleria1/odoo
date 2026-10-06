from odoo import api, fields, models


class AccountAccount(models.Model):
    _inherit = "account.account"

    fiscal_category_id = fields.Many2one(
        comodel_name="account.fiscal.category",
        index="btree_not_null",
        check_company=True,
    )
    rate_ids = fields.One2many(
        comodel_name="account.account.fiscal.rate",
        inverse_name="related_account_id",
    )
    current_rate = fields.Float(compute="_compute_current_rate")

    @api.depends("rate_ids")
    def _compute_current_rate(self) -> None:
        for account in self:
            current_rate = 0
            for rate in account.rate_ids:
                if rate.date_from <= fields.Date.context_today(self):
                    current_rate = rate.rate
                    break
            account.current_rate = current_rate

    @api.onchange("internal_group")
    def _onchange_internal_group(self) -> None:
        if self.internal_group not in ("asset", "expense", "income"):
            self.fiscal_category_id = None


class AccountAccountFiscalRate(models.Model):
    _name = "account.account.fiscal.rate"
    _description = "Fiscal Rate"
    _order = "date_from desc"

    rate = fields.Float(
        string="Fiscal Rate (%)",
        required=True,
    )
    date_from = fields.Date(
        string="Start Date",
        required=True,
    )
    related_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Account",
        index=True,
        required=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        required=True,
    )
