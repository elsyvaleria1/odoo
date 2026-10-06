from odoo import fields, models


class AccountFiscalCategory(models.Model):
    _inherit = "account.fiscal.category"

    car_category = fields.Boolean(
        string="Requires a Vehicle",
        help="The vehicle becomes mandatory while booking any account move.",
    )
