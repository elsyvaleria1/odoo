from odoo import api, fields, models

from ..models.fields import geodesic_length_km


class WizardBaseViewTrailResult(models.TransientModel):
    _name = "wizard.base.view.trail.result"
    _description = "Trail Generation Result"
    _rec_name = "name"

    name = fields.Char(required=True)
    the_trail = fields.GeoLine(srid=4326)
    record_count = fields.Integer()
    wizard_id = fields.Many2one(comodel_name="wizard.base.view.trail")

    trail_color = fields.Char(
        default="#0000FF",
        help="Hex color for trail line",
    )
    trail_width = fields.Integer(
        default=3,
        help="Line width in pixels",
    )
    trail_opacity = fields.Float(
        default=0.8,
        help="Trail transparency (0.0 = transparent, 1.0 = opaque)",
    )

    length_km = fields.Float(
        compute="_compute_length",
        help="Geodesic trail length in kilometers (accurate for WGS84)",
    )

    @api.depends("the_trail")
    def _compute_length(self) -> None:
        for result in self:
            result.length_km = geodesic_length_km(result.the_trail)
