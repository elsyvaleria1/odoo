from collections import defaultdict

from odoo import models
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class StockMove(models.Model):
    _inherit = "stock.move"

    def _action_confirm(self, merge=True, merge_into=False, create_proc=True):
        moves = super()._action_confirm(
            merge=merge, merge_into=merge_into, create_proc=create_proc
        )
        moves._create_quality_checks()
        return moves

    def _post_process_created_moves(self):
        _debug.pipeline("quality_moves_post_process", moves=self)
        super()._post_process_created_moves()
        self.filtered(
            lambda m: m.state not in ("draft", "cancel", "done")
        )._create_quality_checks()

    def _create_quality_checks(self) -> None:
        _debug.pipeline("quality_checks_create", moves=self)
        pick_moves = defaultdict(lambda: self.env["stock.move"])
        for move in self:
            if move.picking_id and move.location_dest_usage != "inventory":
                pick_moves[move.picking_id] |= move
        check_vals_list = self._create_operation_quality_checks(pick_moves)
        for picking, moves in pick_moves.items():
            quality_points_domain = self.env[
                "quality.point"
            ]._get_domain_quality_points(
                moves.product_id, picking.picking_type_id, measure_on="product"
            )
            quality_points = (
                self.env["quality.point"].sudo().search(quality_points_domain)
            )

            if not quality_points:
                continue
            picking_check_vals_list = quality_points._prepare_check_vals_list(
                moves.product_id,
                picking.company_id.id,
                existing_checks=picking.sudo().check_ids,
            )
            for check_value in picking_check_vals_list:
                check_value.update(
                    {
                        "picking_id": picking.id,
                    }
                )
            check_vals_list += picking_check_vals_list
        self.env["quality.check"].sudo().create(check_vals_list)

    def _create_operation_quality_checks(self, pick_moves):
        _debug.pipeline("quality_operation_checks_create", moves=self)
        check_vals_list = []
        for picking, moves in pick_moves.items():
            quality_points_domain = self.env[
                "quality.point"
            ]._get_domain_quality_points(
                moves.product_id, picking.picking_type_id, measure_on="operation"
            )
            existing_point_ids = picking.check_ids.filtered(
                lambda c: c.measure_on == "operation"
            ).point_id.ids
            if existing_point_ids:
                quality_points_domain &= Domain("id", "not in", existing_point_ids)
            quality_points = (
                self.env["quality.point"].sudo().search(quality_points_domain)
            )
            check_vals_list.extend(
                {
                    "point_id": point.id,
                    "team_id": point.team_id.id,
                    "measure_on": "operation",
                    "picking_id": picking.id,
                }
                for point in quality_points
                if point.check_execute_now()
            )
        return check_vals_list

    def _action_cancel(self):
        _debug.pipeline("quality_move_cancel", moves=self)
        res = super()._action_cancel()

        pickings = self.picking_id.sudo()
        pending = pickings.check_ids.filtered(lambda qc: qc.quality_state == "none")
        if not pending:
            return res

        cancelled_products = defaultdict(set)
        fully_cancelled = set()
        for picking in pickings:
            moves_by_product = picking.move_ids.grouped("product_id")
            cancelled_products[picking.id] = {
                product
                for product, moves in moves_by_product.items()
                if all(move.state == "cancel" for move in moves)
            }
            if all(move.state == "cancel" for move in picking.move_ids):
                fully_cancelled.add(picking.id)

        def is_obsolete(qc) -> bool:
            if qc.measure_on == "operation":
                return qc.picking_id.id in fully_cancelled
            return qc.product_id in cancelled_products[qc.picking_id.id]

        pending.filtered(is_obsolete).unlink()

        return res
