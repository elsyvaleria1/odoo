from odoo import models


class StockMove(models.Model):
    _inherit = "stock.move"

    def action_view_reference_no_repair(self) -> dict:
        self.check_singleton()
        source = self.picking_id
        if source and source.has_access("read"):
            return {
                "res_model": source._name,
                "type": "ir.actions.act_window",
                "views": [
                    [
                        self.env.ref(
                            "industry_fsm_repair.repair_view_picking_form_no_repair_access"
                        ).id,
                        "form",
                    ]
                ],
                "res_id": source.id,
            }
        return {
            "res_model": self._name,
            "type": "ir.actions.act_window",
            "views": [[False, "form"]],
            "res_id": self.id,
        }
