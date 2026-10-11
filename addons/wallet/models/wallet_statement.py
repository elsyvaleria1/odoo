from odoo import api, fields, models


class WalletStatement(models.Model):
    _name = "wallet.statement"
    _description = "Electronic Wallet Statement"
    _order = "date_start desc, id desc"

    name = fields.Char(
        compute="_compute_name",
        precompute=True,
        store=True,
    )
    account_id = fields.Many2one(
        comodel_name="wallet.account",
        index=True,
        required=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        related="account_id.company_id",
    )
    currency_id = fields.Many2one(related="company_id.currency_id")
    date_start = fields.Date(required=True)
    date_end = fields.Date(required=True)
    amount_total = fields.Monetary()
    transaction_ids = fields.One2many(
        comodel_name="wallet.transaction",
        inverse_name="statement_id",
    )
    count_transaction = fields.Integer(
        help="How many transactions the issuer reports on the statement."
    )
    attachment_id = fields.Many2one(
        comodel_name="ir.attachment",
        index="btree_not_null",
        ondelete="set null",
        help="The statement as the issuer published it.",
    )

    _account_period_uniq = models.Constraint(
        "UNIQUE(account_id, date_start, date_end)",
        "This account already has a statement for that period.",
    )
    _check_period = models.Constraint(
        "CHECK(date_end >= date_start)",
        "A statement cannot end before it starts.",
    )

    @api.depends("account_id.name", "date_start", "date_end")
    def _compute_name(self):
        for statement in self:
            statement.name = (
                f"{statement.account_id.name or '?'} "
                f"{statement.date_start or '?'} - {statement.date_end or '?'}"
            )
