from odoo import fields, models


class AccountConfig(models.Model):
    _inherit = "account.config"

    collection_hold_credit_sales = fields.Boolean(
        string="Hold Credit Sales of Overdue Collectors",
        help="While a salesperson holds collections past their hand-in date, their "
        "sales orders on credit terms cannot be confirmed.",
    )
