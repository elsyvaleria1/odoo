from odoo import fields, models


class StockWarehouse(models.Model):
    _inherit = "stock.warehouse"

    trip_origin_latitude = fields.Float(
        string="Trip Origin Latitude",
        digits=(10, 7),
        help="Where the delivery trips start and end. Empty uses the coordinates "
        "of the warehouse's address.",
    )
    trip_origin_longitude = fields.Float(
        string="Trip Origin Longitude",
        digits=(10, 7),
    )

    def _trip_origin(self):
        self.check_singleton()
        origin = self._trip_origin_set()
        if origin:
            return origin
        partner = self.partner_id
        if partner.partner_latitude or partner.partner_longitude:
            return partner.partner_latitude, partner.partner_longitude
        return None

    def _trip_origin_set(self):
        self.check_singleton()
        if self.trip_origin_latitude or self.trip_origin_longitude:
            return self.trip_origin_latitude, self.trip_origin_longitude
        return None
