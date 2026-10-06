from odoo import models
from odoo.fields import Domain


class StockQuant(models.Model):
    _inherit = "stock.quant"

    def _get_domain_gather(
        self,
        product_id,
        location_id,
        trace_id=None,
        package_id=None,
        owner_id=None,
        strict=False,
    ):
        domain = super()._get_domain_gather(
            product_id, location_id, trace_id, package_id, owner_id, strict
        )
        if strict or location_id.trip_vehicle_id:
            return domain
        # what rides a vehicle is on the road: a transfer drawing from the
        # place the vehicle loaded at must not reserve it
        if location_id._has_trip_vehicle_descendant():
            domain &= Domain("location_id.trip_vehicle_id", "=", False)
        return domain
