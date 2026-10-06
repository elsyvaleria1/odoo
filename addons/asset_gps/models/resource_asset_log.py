from odoo import fields, models


class ProductAssetLog(models.Model):
    _inherit = "resource.asset.log"

    source = fields.Selection(
        selection_add=[("gps", "GPS Device")],
        ondelete={"gps": "set default"},
    )
