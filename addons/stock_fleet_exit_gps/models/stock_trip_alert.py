from odoo import fields, models


class StockTripAlert(models.Model):
    _inherit = "stock.trip.alert"

    alert_type = fields.Selection(
        selection_add=[("departure_without_route", "Left without an authorised route")],
        ondelete={"departure_without_route": "cascade"},
    )
