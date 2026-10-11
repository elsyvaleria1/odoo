from odoo import models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class StockPickingBatch(models.Model):
    _inherit = "stock.picking.batch"

    def action_picking_map_view(self):
        _debug.lifecycle("batch_map_view_open", batches=self)
        self.check_singleton()
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "stock_fleet_enterprise.stock_picking_action_view_map"
        )
        action["domain"] = [("id", "in", self.picking_ids.ids)]
        return action

    def action_view_batch_from_gantt_view(self) -> dict:
        _debug.lifecycle("batch_gantt_view_open", batches=self)
        self.check_singleton()
        view_id = self.env.ref(
            "stock_fleet_enterprise.stock_picking_batch_view_form_plan_batch"
        ).id
        return {
            "name": self.env._("Plan Batch"),
            "res_model": "stock.picking.batch",
            "view_mode": "form",
            "view_id": view_id,
            "type": "ir.actions.act_window",
            "res_id": self.id,
            "target": "new",
        }
