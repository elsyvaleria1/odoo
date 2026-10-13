from odoo import models
from odoo.tools import frozendict


class AccountMoveMatch(models.Model):
    _name = "account.move.match"
    _inherit = "mixin.account.document.match"
    _description = "Accounting Document Sources"
    _auto = False
    _order = "date desc, name desc"
    _rec_names_search = ["name", "reference"]
    _depends = frozendict(
        {
            "account.move": [
                "name",
                "ref",
                "partner_id",
                "date",
                "amount_untaxed",
                "currency_id",
                "company_id",
                "invoice_user_id",
                "move_type",
            ],
        }
    )
