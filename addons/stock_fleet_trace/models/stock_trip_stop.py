from odoo import fields, models


class StockTripStop(models.Model):
    """One delivery on one trip: what it weighed when it boarded and what was lost."""

    _name = "stock.trip.stop"
    _description = "Trip Delivery Weight"
    _order = "batch_id, sequence, id"

    batch_id = fields.Many2one(
        comodel_name="stock.picking.batch",
        string="Trip",
        index=True,
        required=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        related="batch_id.company_id",
    )
    picking_id = fields.Many2one(
        comodel_name="stock.picking",
        string="Delivery",
        index=True,
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer()
    weight_departure = fields.Float(
        string="Weight at Departure",
        digits="Stock Weight",
        help="Theoretical weight of this delivery when it boarded this trip: at "
        "loading, or at the handover for a rescue trip.",
    )
    weight_written_off = fields.Float(
        string="Weight Written Off",
        digits="Stock Weight",
        help="Weight of this delivery's goods that approved incidents of this trip "
        "wrote off.",
    )

    _batch_picking_uniq = models.Constraint(
        "UNIQUE(batch_id, picking_id)",
        "A delivery boards a trip once.",
    )
