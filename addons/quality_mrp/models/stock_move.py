from collections import defaultdict

from odoo import models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class StockMove(models.Model):
    _inherit = "stock.move"

    def _action_confirm(self, merge=True, merge_into=False, create_proc=True):
        moves = super()._action_confirm(
            merge=merge, merge_into=merge_into, create_proc=create_proc
        )
        moves._create_quality_checks_for_mo()

        return moves

    def _search_quality_points(self, product_id, picking_type_id, measure_on):
        quality_points_domain = self.env["quality.point"]._get_domain_quality_points(
            product_id, picking_type_id, measure_on=measure_on
        )
        quality_points_domain = self.env["quality.point"]._get_domain_for_production(
            quality_points_domain
        )
        return self.env["quality.point"].sudo().search(quality_points_domain)

    def _create_quality_checks_for_mo(self) -> None:
        mo_moves = defaultdict(lambda: self.env["stock.move"])
        check_vals_list = []
        for move in self:
            if move.production_id and move.location_dest_usage != "inventory":
                mo_moves[move.production_id] |= move

        points_by_question = {}

        def search_points(products, picking_type, measure_on):
            question = (frozenset(products.ids), picking_type.id, measure_on)
            if question not in points_by_question:
                points_by_question[question] = self._search_quality_points(
                    products, picking_type, measure_on
                )
            return points_by_question[question]

        for production, moves in mo_moves.items():
            quality_points = search_points(
                moves.product_id, production.picking_type_id, "product"
            )

            quality_points |= search_points(
                production.product_id, production.picking_type_id, "move_line"
            )

            if not quality_points:
                _debug.logic(
                    "qc_points_none", production=production.id, measure_on="product"
                )
                continue
            mo_check_vals_list = quality_points._prepare_check_vals_list(
                moves.product_id,
                production.company_id.id,
                existing_checks=production.sudo().check_ids,
            )
            for check_value in mo_check_vals_list:
                check_value.update(
                    {
                        "production_id": production.id,
                    }
                )
            check_vals_list += mo_check_vals_list

        for production in mo_moves:
            existing_point_ids = (
                production.sudo()
                .check_ids.filtered(lambda c: c.measure_on == "operation")
                .point_id.ids
            )
            quality_points_operation = search_points(
                production.move_finished_ids.product_id,
                production.picking_type_id,
                "operation",
            ).filtered_domain([("id", "not in", existing_point_ids)])
            _debug.logic(
                "qc_operation_points",
                production=production.id,
                already_checked=len(existing_point_ids),
                new_points=len(quality_points_operation),
            )

            for point in quality_points_operation:
                if point.check_execute_now():
                    check_vals_list.append(
                        {
                            "point_id": point.id,
                            "team_id": point.team_id.id,
                            "measure_on": "operation",
                            "production_id": production.id,
                        }
                    )

        _debug.pipeline(
            "qc_checks_created",
            moves=self,
            productions=len(mo_moves),
            checks=len(check_vals_list),
        )
        self.env["quality.check"].sudo().create(check_vals_list)
