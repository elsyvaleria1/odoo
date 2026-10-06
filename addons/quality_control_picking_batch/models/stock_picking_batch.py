from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class StockPickingBatch(models.Model):
    _inherit = "stock.picking.batch"

    quality_check_todo = fields.Boolean(compute="_compute_quality_check_todo")

    @api.depends("picking_ids.quality_check_todo")
    def _compute_quality_check_todo(self) -> None:
        _debug.perf.count("batch_quality_todo_compute", batches=self)
        for batch in self:
            batch.quality_check_todo = any(
                batch.picking_ids.mapped("quality_check_todo")
            )

    def action_view_quality_check_wizard(self):
        _debug.pipeline("batch_quality_wizard_open", batches=self)
        check_ids = self.picking_ids.check_ids.filtered(
            lambda check: check.quality_state == "none"
        )
        return check_ids.action_view_quality_check_wizard()
