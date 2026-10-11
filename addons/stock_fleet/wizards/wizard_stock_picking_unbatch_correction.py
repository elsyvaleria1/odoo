from odoo import api, fields, models
from odoo.exceptions import UserError


class WizardStockPickingUnbatchCorrection(models.TransientModel):

    _name = "wizard.stock.picking.unbatch.correction"
    _description = "Remove Transfers from Trip"

    batch_id = fields.Many2one(
        comodel_name="stock.picking.batch",
        string="Trip",
        required=True,
        ondelete="cascade",
    )
    picking_ids = fields.Many2many(
        comodel_name="stock.picking",
        string="Transfers",
        compute="_compute_picking_ids",
        store=True,
        readonly=False,
        domain="[('batch_id', '=', batch_id), ('state', 'not in', ('done', 'cancel'))]",
        help="The pending transfers that come off the trip; all of them unless some "
        "are unticked.",
    )
    reason_id = fields.Many2one(
        comodel_name="stock.picking.unbatch.reason",
        required=True,
        domain="[('moment', 'in', ('before_departure', 'any'))]",
    )
    note = fields.Text(help="What the reason leaves unsaid.")

    @api.depends("batch_id")
    def _compute_picking_ids(self):
        for wizard in self:
            wizard.picking_ids = wizard.batch_id.picking_ids.filtered(
                lambda picking: picking.state not in ("done", "cancel")
            )

    def action_confirm(self):
        self.check_singleton()
        trip = self.batch_id
        if not trip.date_departure:
            raise UserError(
                self.env._(
                    "Trip %s has not left: take the transfers off it from the batch.",
                    trip.name,
                )
            )
        if self.reason_id.moment == "on_route":
            raise UserError(
                self.env._(
                    "%(reason)s says the goods travelled and came back: register the "
                    "transfer as not delivered instead.",
                    reason=self.reason_id.name,
                )
            )
        if not self.picking_ids:
            raise UserError(self.env._("Choose the transfers to take off the trip."))
        stuck = self.picking_ids.filtered(
            lambda picking: (
                picking.batch_id != trip or picking.state in ("done", "cancel")
            )
        )
        if stuck:
            raise UserError(
                self.env._(
                    "%(pickings)s cannot come off trip %(batch)s: only its pending "
                    "transfers can.",
                    pickings=", ".join(stuck.mapped("name")),
                    batch=trip.name,
                )
            )
        reason = self.reason_id.name
        if self.note:
            reason = f"{reason}: {self.note}"
        self.picking_ids._take_off_trip_as_correction(reason)
        return {"type": "ir.actions.act_window_close"}
