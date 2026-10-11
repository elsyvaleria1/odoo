from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    sendcloud_parcel_ref = fields.Json(
        string="Sendcloud Parcel Reference",
        copy=False,
    )
    sendcloud_return_parcel_ref = fields.Json(copy=False)

    def _get_warehouse_name(self):
        self.check_singleton()
        return self.location_id.warehouse_id.name
