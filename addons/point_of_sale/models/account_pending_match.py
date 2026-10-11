from odoo import fields, models


class AccountPendingMatch(models.Model):
    _inherit = "account.pending.match"

    origin = fields.Selection(
        selection_add=[("point_of_sale", "Point of Sale invoicing")],
        ondelete={"point_of_sale": "cascade"},
    )
