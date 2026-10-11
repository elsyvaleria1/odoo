from odoo import models


class FleetVehicleTag(models.Model):
    _name = "fleet.vehicle.tag"
    _description = "Vehicle Tag"
    _inherit = ["mixin.tag"]
