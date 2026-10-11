from odoo import api, fields, models
from odoo.api import ValuesType
from odoo.libs.debug_log import DebugLog
from odoo.tools.authority_keys import declare_authority_keys

declare_authority_keys("quality_control", "no_checks")

_debug = DebugLog(__name__)


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    check_ids = fields.One2many(
        comodel_name="quality.check",
        inverse_name="move_line_id",
        string="Checks",
    )
    check_state = fields.Selection(
        selection=[
            ("no_checks", "No checks"),
            ("in_progress", "Some checks to be done"),
            ("pass", "All checks passed"),
            ("fail", "Some checks failed"),
        ],
        compute="_compute_check_state",
    )

    @api.depends("check_ids")
    def _compute_check_state(self) -> None:
        for line in self:
            if not line.check_ids:
                line.check_state = "no_checks"
            elif line.check_ids.filtered(lambda check: check.quality_state == "none"):
                line.check_state = "in_progress"
            elif line.check_ids.filtered(lambda check: check.quality_state == "fail"):
                line.check_state = "fail"
            else:
                line.check_state = "pass"

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        if self.env.context.get("no_checks"):
            return lines
        lines._filtered_applicable_for_quality_check()._create_check()
        return lines

    def write(self, vals):
        if self._create_quality_check_at_write(vals):
            self.filtered(
                lambda ml: ml.state != "done" and not ml.sudo().check_ids
            )._create_check()
        return super().write(vals)

    def unlink(self):
        self.sudo()._unlink_quality_check()
        return super().unlink()

    def action_view_quality_check_wizard(self):
        return self.check_ids.action_view_quality_check_wizard()

    def _unlink_quality_check(self) -> None:
        _debug.lifecycle("line_quality_check_unlink", lines=self)
        self.check_ids.filtered(lambda qc: qc._check_to_unlink()).unlink()

    def _create_quality_check_at_write(self, vals):
        _debug.lifecycle("line_quality_check_at_write", lines=self)
        return vals.get("quantity")

    def _create_check(self) -> None:
        _debug.pipeline("line_quality_check_create", lines=self)
        check_values_list = []
        quality_points_domain = self.env["quality.point"]._get_domain_quality_points(
            self.product_id, self.move_id.picking_type_id, measure_on="move_line"
        )
        quality_points = self.env["quality.point"].sudo().search(quality_points_domain)

        categ_ids_by_product = {
            product: {
                int(categ_id)
                for categ_id in (product.categ_id.parent_path or "").split("/")[:-1]
            }
            for product in self.product_id
        }
        quality_points_by_product_picking_type = {}
        for quality_point in quality_points:
            if not quality_point.product_ids and not quality_point.product_category_ids:
                keys = [
                    (None, picking_type)
                    for picking_type in quality_point.picking_type_ids
                ]
            else:
                point_categ_ids = set(quality_point.product_category_ids.ids)
                keys = [
                    (product, picking_type)
                    for product, categ_ids in categ_ids_by_product.items()
                    if product in quality_point.product_ids
                    or categ_ids & point_categ_ids
                    for picking_type in quality_point.picking_type_ids
                ]
            for key in keys:
                quality_points_by_product_picking_type.setdefault(key, set()).add(
                    quality_point.id
                )

        settled = quality_points._get_execute_now_by_point()

        for ml in self:
            quality_points_product = quality_points_by_product_picking_type.get(
                (ml.product_id, ml.move_id.picking_type_id), set()
            )
            quality_points_all_products = ml._get_quality_points_all_products(
                quality_points_by_product_picking_type
            )
            point_ids = quality_points_product | quality_points_all_products
            check_values_list.extend(
                ml._prepare_check_vals(quality_point)
                for quality_point in quality_points.filtered(
                    lambda point, point_ids=point_ids: point.id in point_ids
                )
                if quality_point._is_execution_required(settled)
            )
        if check_values_list:
            self.env["quality.check"].sudo().create(check_values_list)

    def _filtered_applicable_for_quality_check(self):
        _debug.logic("lines_quality_applicable", lines=self)
        return self.filtered(lambda line: line.quantity != 0)

    def _prepare_check_vals(self, quality_point) -> ValuesType:
        return {
            **quality_point._prepare_check_vals(self.product_id, self.company_id.id),
            "picking_id": self.picking_id.id,
            "move_line_id": self.id,
            "lot_name": self.lot_name,
        }

    def _get_quality_points_all_products(self, quality_points_by_product_picking_type):
        return quality_points_by_product_picking_type.get(
            (None, self.move_id.picking_type_id), set()
        )

    def _is_checkable_from_context(self) -> bool:
        _debug.logic("line_quality_checkable_context", lines=self)
        if self.env.context.get("picking_validation"):
            return bool(self.move_id.picked)
        return True

    def _is_checkable(self, check_picked=False) -> bool:
        _debug.logic("line_quality_checkable", lines=self, check_picked=check_picked)
        self.check_singleton()
        if self.product_uom_id.is_zero(self.quantity):
            return False
        if check_picked:
            if not self._is_checkable_from_context():
                return False
        return True
