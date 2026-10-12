from odoo import fields, models


class WizardStockPickingDeliveryProof(models.TransientModel):
    _name = "wizard.stock.picking.delivery.proof"
    _description = "Signed Delivery Slip"

    picking_id = fields.Many2one(
        comodel_name="stock.picking",
        required=True,
        ondelete="cascade",
    )
    delivery_proof = fields.Image(
        string="Signed Delivery Slip",
        attachment=False,
        max_width=1920,
        max_height=1920,
        required=True,
    )
    resume = fields.Selection(
        selection=[("deliver", "Deliver")],
        help="Deliver the transfer once the photo is in, as the Delivered button "
        "asked; empty to only keep the photo and repeat the refused action.",
    )

    def action_confirm(self):
        self.check_singleton()
        picking = self.picking_id
        picking.delivery_proof = self.delivery_proof
        result = picking.action_deliver() if self.resume == "deliver" else None
        if isinstance(result, dict):
            return result
        return {"type": "ir.actions.act_window_close"}
