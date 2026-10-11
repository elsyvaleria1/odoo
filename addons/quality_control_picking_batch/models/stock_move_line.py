from odoo import models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    def write(self, vals):
        _debug.lifecycle("batch_quality_line_write", lines=self, fields=len(vals))
        res = super().write(vals)
        if "picking_id" in vals:
            self.check_ids.filtered(
                lambda qc: qc.measure_on == "move_line"
            ).picking_id = vals["picking_id"]
        return res
