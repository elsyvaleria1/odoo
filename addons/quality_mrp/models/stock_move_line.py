from odoo import models
from odoo.api import ValuesType
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    def write(self, vals):
        mark = self._deletion_mark()
        res = super().write(vals)
        _debug.lifecycle("write", lines=self, fields=list(vals))
        if not vals.get("trace_id"):
            return res
        # a move line write can DELETE members of `self`: stock's reservation
        # engine settles an over-allocation by unlinking competing
        # reservations, and a line of this very batch can be among them.
        # `trace_id` is one of the fields that reaches that path, so reading
        # `check_ids` off the pre-write recordset dereferences a deleted row.
        survivors = self._survivors_since(mark)
        if survivors.sudo().check_ids:
            survivors.check_ids.filtered(
                lambda qc: (
                    qc.test_type
                    in ("register_consumed_materials", "register_byproducts")
                )
            ).trace_ids = vals["trace_id"]
        return res

    def _prepare_check_vals(self, quality_point) -> ValuesType:
        vals = super()._prepare_check_vals(quality_point)
        vals.update(
            {
                "production_id": self.move_id.production_id.id
                or self.move_id.raw_material_production_id.id
            }
        )
        return vals

    def _get_quality_points_all_products(self, quality_points_by_product_picking_type):
        if self.move_id.raw_material_production_id:
            return set()
        else:
            return super()._get_quality_points_all_products(
                quality_points_by_product_picking_type
            )

    def _create_quality_check_at_write(self, vals):
        if self.move_id.production_id or self.move_id.raw_material_production_id:
            return False
        return super()._create_quality_check_at_write(vals)

    def _filtered_applicable_for_quality_check(self):
        ok_lines = self.filtered(lambda sml: sml.move_id.raw_material_production_id)
        done_lines = self.filtered(
            lambda sml: sml.product_id == sml.move_id.production_id.product_id
        )
        return (
            ok_lines
            | super(
                StockMoveLine, self - ok_lines - done_lines
            )._filtered_applicable_for_quality_check()
        )
