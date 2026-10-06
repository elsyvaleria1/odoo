from odoo import models


class WizardStockWarehouseOrderpointUpdateReplenishmentOption(models.TransientModel):
    _inherit = "wizard.stock.warehouse.orderpoint.update.replenishment.option"

    def action_select_route(self):
        if self.env.context.get("replenish_id"):
            replenish = self.env["wizard.product.product.replenish"].browse(
                self.env.context.get("replenish_id")
            )
            replenish.route_id = self.route_id.id
            return {
                "type": "ir.actions.act_window",
                "name": "Replenish",
                "res_model": "wizard.product.product.replenish",
                "res_id": replenish.id,
                "target": "new",
                "view_mode": "form",
            }
        return super().action_select_route()
