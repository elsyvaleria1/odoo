from odoo import fields, models

TRACK_POINT_COLORS = {
    "stop": "#6c757d",
    "departure": "#0d6efd",
    "return": "#6610f2",
    "arrival": "#ffc107",
    "delivery": "#198754",
    "not_delivered": "#fd7e14",
    "incident": "#dc3545",
    "alert": "#d63384",
}


class WizardStockTripTrackPoint(models.TransientModel):

    _name = "wizard.stock.trip.track.point"
    _description = "Trip Track Point"
    _order = "date, id"

    name = fields.Char(required=True)
    batch_id = fields.Many2one(
        comodel_name="stock.picking.batch",
        string="Trip",
        required=True,
        ondelete="cascade",
    )
    trail_result_id = fields.Many2one(
        comodel_name="wizard.device.device.view.trail.result",
        string="Trail",
        ondelete="cascade",
        help="The trail drawn with these points: the map shows the points of the "
        "trails it displays.",
    )
    kind = fields.Selection(
        selection=[
            ("stop", "Planned stop"),
            ("departure", "Departure"),
            ("arrival", "Arrival"),
            ("delivery", "Delivery"),
            ("not_delivered", "Not delivered"),
            ("incident", "Incident"),
            ("alert", "GPS alert"),
            ("return", "Return"),
        ],
        required=True,
    )
    date = fields.Datetime()
    label = fields.Char(
        help="The kind and time as the popup shows them, in the user's language "
        "and time zone.",
    )
    color = fields.Char()
    the_point = fields.GeoPoint(
        string="Place",
        srid=4326,
    )
