from odoo import fields, models


class StockPackageType(models.Model):
    _inherit = "stock.package.type"

    package_carrier_type = fields.Selection(selection_add=[("easypost", "Easypost")])
    easypost_carrier = fields.Char(
        string="Carrier Prefix",
        index=True,
    )
