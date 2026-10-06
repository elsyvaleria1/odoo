from odoo import fields, models


class StockPickingUnbatchReason(models.Model):
    """Why a transfer comes off a trip, from a catalogue the leaders extend."""

    _name = "stock.picking.unbatch.reason"
    _description = "Trip Removal Reason"
    _order = "sequence, id"

    name = fields.Char(
        translate=True,
        required=True,
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        comodel_name="res.company",
        index=True,
        help="Leave it empty to offer the reason to every company.",
    )
    moment = fields.Selection(
        selection=[
            ("before_departure", "Before departure"),
            ("on_route", "On the route"),
            ("any", "Before departure or on the route"),
        ],
        default="on_route",
        required=True,
        help="When the reason can be given: while the trip is assembled, once it "
        "has left, or at either moment.",
    )
    accountable = fields.Selection(
        selection=[
            ("customer", "Customer"),
            ("customer_data", "Customer data"),
            ("operations", "Our operation"),
            ("fleet", "Vehicles"),
            ("fulfilment", "Picking or quality"),
            ("credit", "Credit and collections"),
            ("internal", "Internal decision"),
        ],
        required=True,
        help="Who has to act so that the failure does not repeat; each reason points "
        "to a different one, so the undelivered count says what to correct.",
    )
