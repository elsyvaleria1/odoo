from odoo import fields, models

ALERT_TYPES = [
    ("departure_without_trip", "Left without a trip"),
    ("departure_not_loaded", "Left before loading"),
    ("departure_blocked", "Left but the trip could not depart"),
    ("outcome_without_visit", "Outcome without a GPS visit"),
    ("customer_without_location", "Customer without coordinates"),
    ("unplanned_stop", "Unplanned stop"),
    ("harsh_driving", "Harsh driving"),
    ("gps_silent", "GPS silent"),
    ("returned_pending", "Back with stops pending"),
    ("reading_conflict", "GPS contradicts a captured reading"),
]


class StockTripAlert(models.Model):

    _name = "stock.trip.alert"
    _description = "Trip Alert"
    _order = "date desc, id desc"
    _rec_name = "alert_type"

    alert_type = fields.Selection(
        selection=ALERT_TYPES,
        string="Alert",
        index=True,
        required=True,
    )
    date = fields.Datetime(
        index=True,
        required=True,
    )
    vehicle_id = fields.Many2one(
        comodel_name="resource.asset.vehicle",
        index=True,
        required=True,
        ondelete="cascade",
    )
    batch_id = fields.Many2one(
        comodel_name="stock.picking.batch",
        string="Trip",
        index="btree_not_null",
        ondelete="cascade",
    )
    picking_id = fields.Many2one(
        comodel_name="stock.picking",
        string="Delivery",
    )
    partner_id = fields.Many2one(related="picking_id.partner_id")
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        required=True,
    )
    latitude = fields.Float(digits=(10, 7))
    longitude = fields.Float(digits=(10, 7))
    duration_minutes = fields.Integer(string="Minutes")
    note = fields.Char()
    state = fields.Selection(
        selection=[("open", "Open"), ("reviewed", "Reviewed")],
        default="open",
        required=True,
    )
    reviewed_uid = fields.Many2one(
        comodel_name="res.users",
        string="Reviewed By",
        readonly=True,
    )

    _alert_uniq = models.Constraint(
        "UNIQUE NULLS NOT DISTINCT (alert_type, vehicle_id, date, picking_id)",
        "This alert was already raised.",
    )

    def action_review(self):
        self.write({"state": "reviewed", "reviewed_uid": self.env.uid})
