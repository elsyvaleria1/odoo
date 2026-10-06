from odoo import fields, models


class DeviceStateBoundary(models.Model):
    _name = "device.state.boundary"
    _description = "State/Province Boundary"
    _order = "country_id, name"

    name = fields.Char(
        index=True,
        required=True,
    )
    country_id = fields.Many2one(
        comodel_name="res.country",
        index=True,
        required=True,
        ondelete="cascade",
        help="Country this boundary belongs to",
    )
    state_id = fields.Many2one(
        comodel_name="res.country.state",
        index=True,
        ondelete="cascade",
        help="Link to res.country.state for this boundary",
    )
    geom = fields.GeoMultiPolygon(
        srid=4326,
        help="MultiPolygon geometry of state boundary",
    )
