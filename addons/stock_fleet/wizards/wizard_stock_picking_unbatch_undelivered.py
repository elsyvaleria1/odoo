from odoo import fields, models
from odoo.exceptions import UserError


class WizardStockPickingUnbatchUndelivered(models.TransientModel):

    _name = "wizard.stock.picking.unbatch.undelivered"
    _description = "Undelivered Transfer"

    picking_id = fields.Many2one(
        comodel_name="stock.picking",
        required=True,
        ondelete="cascade",
    )
    reason_id = fields.Many2one(
        comodel_name="stock.picking.unbatch.reason",
        required=True,
        domain="[('moment', 'in', ('on_route', 'any'))]",
    )
    note = fields.Text(help="What the driver adds to the reason.")

    def action_confirm(self):
        self.check_singleton()
        if self.reason_id.moment == "before_departure":
            raise UserError(
                self.env._(
                    "%(reason)s is a reason to take a transfer off a trip before it "
                    "leaves, not to send it back from the route.",
                    reason=self.reason_id.name,
                )
            )
        reason = self.reason_id.name
        if self.note:
            reason = f"{reason}: {self.note}"
        self.picking_id.delivery_failure_reason_id = self.reason_id
        self.picking_id._register_delivery_failure(reason)
        return {"type": "ir.actions.act_window_close"}
