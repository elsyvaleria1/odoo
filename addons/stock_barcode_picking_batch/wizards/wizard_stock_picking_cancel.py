from odoo import fields, models


class WizardStockPickingCancel(models.TransientModel):
    _inherit = "wizard.stock.picking.cancel"

    batch_id = fields.Many2one(
        comodel_name="stock.picking.batch",
        string="Batch Transfer",
        readonly=True,
    )
    batch_name = fields.Char(
        related="batch_id.name",
        string="Batch Transfer Name",
        readonly=True,
    )

    def action_cancel_operation(self) -> dict:
        if self.batch_id:
            res = self.batch_id.action_cancel()
            return {"type": "ir.actions.act_window_close", "infos": {"cancelled": res}}
        return super().action_cancel_operation()
