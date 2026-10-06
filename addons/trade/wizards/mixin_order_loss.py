from odoo import fields, models


class MixinOrderLoss(models.AbstractModel):
    _name = "mixin.order.loss"
    _description = "Mark Orders as Lost"

    outcome = fields.Selection(
        selection=[
            ("lost", "Lost"),
            ("rejected", "Rejected"),
        ],
        default="lost",
        required=True,
        help="Lost: the counterparty went elsewhere. Rejected: we declined their "
        "offer.",
    )
    loss_reason_id = fields.Many2one(
        comodel_name="loss.reason",
        string="Reason",
        domain=lambda self: self._get_order_model()._domain_loss_reason_id(),
    )
    loss_note = fields.Text(string="Details")

    def _get_order_model(self):
        if "order_ids" not in self._fields:
            return self.env["mixin.order"]
        return self.env[self._fields["order_ids"].comodel_name]

    def action_close(self):
        self.check_singleton()
        self.order_ids._close_as(
            self.outcome,
            loss_reason=self.loss_reason_id,
            note=self.loss_note,
        )
        return {"type": "ir.actions.act_window_close"}
