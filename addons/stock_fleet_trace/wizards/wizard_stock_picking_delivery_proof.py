from odoo import api, fields, models
from odoo.exceptions import ValidationError


class WizardStockPickingDeliveryProof(models.TransientModel):
    _inherit = "wizard.stock.picking.delivery.proof"

    delivery_proof = fields.Image(
        required=False,
    )
    receiver_name = fields.Char(
        string="Received By",
        help="Who took the goods, written by them or by whoever delivered: with "
        "their signature it counts as the signed slip.",
    )
    signature = fields.Image(
        string="Signature",
        attachment=False,
        max_width=1024,
        max_height=1024,
        help="The signature of whoever received, on this screen.",
    )

    @api.constrains("delivery_proof", "receiver_name", "signature")
    def _check_evidence(self) -> None:
        for wizard in self:
            if not wizard.delivery_proof and not (
                wizard.receiver_name and wizard.signature
            ):
                raise ValidationError(
                    self.env._(
                        "Take the photo of the signed delivery slip, or have whoever "
                        "received write their name and sign here."
                    )
                )

    def action_confirm(self):
        self.check_singleton()
        if self.signature and self.receiver_name:
            self.picking_id.write(
                {
                    "trip_receiver_name": self.receiver_name.strip(),
                    "signature": self.signature,
                }
            )
            if not self.delivery_proof:
                problem = self.picking_id._customer_signature_problem()
                if problem:
                    raise ValidationError(
                        self.env._(
                            "The signature does not count as the customer's: "
                            "%(problem)s.",
                            problem=problem,
                        )
                    )
        return super().action_confirm()
