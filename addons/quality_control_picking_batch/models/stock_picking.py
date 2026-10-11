from odoo import models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class StockPickingBatch(models.Model):
    _inherit = "stock.picking"

    def _add_to_wave_post_picking_split_hook(self):
        _debug.pipeline("batch_quality_wave_split_hook", batches=self)
        super()._add_to_wave_post_picking_split_hook()
        checks_by_picking = self.check_ids.filtered(
            lambda qc: (
                qc.measure_on in ("operation", "product") and qc.quality_state == "none"
            )
        ).grouped("picking_id")
        checks_ids_to_unlink = set()
        for picking, checks in checks_by_picking.items():
            products = picking.move_ids.product_id
            for check in checks:
                if check.measure_on == "operation" or (
                    check.measure_on == "product" and check.product_id not in products
                ):
                    checks_ids_to_unlink.add(check.id)
        self.env["quality.check"].browse(checks_ids_to_unlink).sudo().unlink()
        self.move_ids.sudo()._create_quality_checks()
