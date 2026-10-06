from collections import defaultdict

from odoo import Command, api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardProjectTaskUpdateProductLot(models.TransientModel):
    _name = "wizard.project.task.update.product.lot"
    _description = "Track Stock"

    task_id = fields.Many2one(comodel_name="project.task")
    product_id = fields.Many2one(comodel_name="product.product")
    tracking = fields.Selection(related="product_id.tracking")

    tracking_line_ids = fields.One2many(
        comodel_name="wizard.project.task.update.product.lot.line",
        inverse_name="wizard_tracking_line",
        export_string_translation=False,
    )
    tracking_validated_line_ids = fields.One2many(
        comodel_name="wizard.project.task.update.product.lot.line",
        inverse_name="wizard_tracking_line_validated",
        export_string_translation=False,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        export_string_translation=False,
    )
    is_same_warehouse = fields.Boolean(
        export_string_translation=False,
        compute="_compute_is_same_warehouse",
    )

    @api.depends("tracking_line_ids.is_same_warehouse")
    def _compute_is_same_warehouse(self) -> None:
        for tracking in self:
            tracking.is_same_warehouse = all(
                tracking.tracking_line_ids.mapped("is_same_warehouse")
            )

    def _update_lot_id(self, sale_line, tracking_line) -> None:
        for move in sale_line.move_ids:
            for ml in move.move_line_ids:
                if ml.trace_id == sale_line.fsm_trace_id:
                    ml.trace_id = tracking_line.trace_id

    def _get_moves_dict(self, sale_order):
        _debug.logic("fsm_moves_dict_build", wizards=self, order=sale_order.id)
        default_warehouse = self.env.user._get_default_warehouse_id()
        triggering_rule = default_warehouse.delivery_route_id.rule_ids[0]
        if (
            triggering_rule.location_dest_id
            != triggering_rule.picking_type_id.default_location_dest_id
        ):
            return {}
        pickings_to_update = sale_order.picking_ids.filtered(
            lambda p: (
                p.location_dest_id
                in (
                    default_warehouse.wh_pack_stock_loc_id
                    | default_warehouse.wh_output_stock_loc_id
                )
                and p.state not in ["done", "cancel"]
            )
        )
        move_read_group = self.env["stock.move"]._read_group(
            [
                ("picking_id", "in", pickings_to_update.ids),
                ("product_id", "=", self.product_id.id),
            ],
            ["picking_id"],
            ["id:recordset"],
        )
        return dict(move_read_group)

    def _remove_qty_from_intermediate_delivery(
        self, moves_from_intermediate_pickings, lot, qty_removed, deleted_line=False
    ) -> None:
        _debug.pipeline("fsm_intermediate_qty_remove", wizards=self)
        for pick in moves_from_intermediate_pickings:
            qty_done_diff = qty_removed
            for move in moves_from_intermediate_pickings[pick]:
                if move.state == "done, cancel":
                    continue
                for move_line in move.move_line_ids:
                    if move_line.quantity > 0:
                        if not move_line.trace_id:
                            move_line.trace_id = lot
                        elif move_line.trace_id != lot:
                            continue
                        new_line_qty = max(0, move_line.quantity + qty_done_diff)
                        qty_done_diff += move_line.quantity - new_line_qty
                        previous_qty = move_line.quantity
                        move_line.quantity = new_line_qty
                        if (
                            deleted_line
                            and move.warehouse_id
                            != self.task_id.sale_order_id.warehouse_id
                        ):
                            move.product_uom_qty -= previous_qty - new_line_qty
                        if qty_done_diff == 0:
                            break
                if qty_done_diff == 0:
                    break

    def _add_qty_to_intermediate_delivery_batch(
        self, moves_from_intermediate_pickings, lot, qty_added
    ):
        ml_to_create = []
        for pick in moves_from_intermediate_pickings:
            for move in moves_from_intermediate_pickings[pick]:
                if move.state == "done, cancel":
                    continue
                new_line_needed = True
                for ml in move.move_line_ids:
                    if not ml.trace_id or ml.trace_id == lot:
                        if ml.quantity != qty_added:
                            ml.quantity = qty_added
                        new_line_needed = False
                        break
                # if no ml were available, create a new one
                move = (
                    moves_from_intermediate_pickings[pick][0]
                    if moves_from_intermediate_pickings[pick]
                    else False
                )
                if new_line_needed and move:
                    ml_vals = move._prepare_move_line_vals(quantity=0)
                    ml_vals["quantity"] = qty_added
                    ml_vals["trace_id"] = lot.id
                    ml_to_create.append(ml_vals)
        return ml_to_create

    def _add_qty_to_intermediate_delivery(
        self, moves_from_intermediate_pickings, line, qty_added
    ) -> None:
        _debug.pipeline("fsm_intermediate_qty_add", wizards=self)
        self.env["stock.move.line"].create(
            self._add_qty_to_intermediate_delivery_batch(
                moves_from_intermediate_pickings, line.trace_id, qty_added
            )
        )

    def action_generate_lot(self) -> None:
        _debug.pipeline("fsm_lot_generate", wizards=self)
        self.check_singleton()
        if self.tracking_line_ids.filtered(lambda l: not l.trace_id):
            raise UserError(self.env._("Each line needs a Lot/Serial Number"))

        section_id = self.env.context.get("section_id") or False
        sale_lines_remove = self.task_id.sale_order_id.line_ids.sudo().filtered(
            lambda line: (
                line.product_id == self.product_id
                and line.id not in self.tracking_line_ids.sale_order_line_id.ids
                and line.task_id == self.task_id
                and line.get_line_parent_section().id == section_id
            )
        )
        # create the new sale_lines from the wizard
        move_line_qty_per_lot_id = defaultdict(int)
        new_lines = self.tracking_line_ids.filtered(
            lambda line: not line.sale_order_line_id
        )
        for line in new_lines:
            qty = line.quantity if self.tracking == "lot" else 1
            child_field = self.env.context.get("child_field", "line_ids")
            sequence = self.task_id.sale_order_id._get_new_line_sequence(
                child_field, section_id
            )
            vals = {
                "order_id": self.task_id.sale_order_id.id,
                "product_id": self.product_id.id,
                "product_qty": qty,
                "task_id": self.task_id.id,
                "fsm_trace_id": line.trace_id.id,
                "sequence": sequence,
            }
            if self.task_id.under_warranty:
                vals["price_unit"] = 0
            move_line_qty_per_lot_id[line.trace_id] += qty
            self.env["sale.order.line"].sudo().with_context(
                industry_fsm_stock_tracking=True
            ).create(vals)

        dict_moves_per_picking = self._get_moves_dict(self.task_id.sale_order_id)
        self.env["stock.move"].check_access("write")

        # set the qty to 0 for the sol and the deliveries from the deleted wizard line
        for sl in sale_lines_remove:
            if sl.qty_transferred == 0 and sl.fsm_trace_id:
                # if dict_moves_per_picking:  # handles 2/3 ways deliveries
                #     self._remove_qty_from_intermediate_delivery(dict_moves_per_picking, sl.fsm_trace_id, 0-(sl.product_qty - sl.qty_transferred), deleted_line=True)
                editable_moves = sl.move_ids.filtered(
                    lambda m: m.state not in ["done", "cancel"]
                )
                editable_moves.move_line_ids.unlink()
                for m in editable_moves:
                    m.trace_ids = [Command.unlink(sl.fsm_trace_id.id)]
                sl.fsm_trace_id = False
                # If the warehouse of the delivery is different from the one of the sale_order, the stock.rule.run() will not handle the moves correctly.
                # We have to manually set the product_uom_qty and cancel the moves
                if (
                    sl.order_id.warehouse_id
                    != self.env.user._get_default_warehouse_id()
                ):
                    editable_moves.product_uom_qty = 0
                    editable_moves.state = "cancel"
            sl.product_qty = sl.qty_transferred

        # update the sol and deliveries according to the modification of the wizard lines
        for line in self.tracking_line_ids:
            qty = line.quantity if self.tracking == "lot" else 1
            sol = line.sale_order_line_id
            if sol:
                if dict_moves_per_picking:  # handles 2/3 ways deliveries
                    if sol.fsm_trace_id == line.trace_id:
                        current_qty_demand = sol.product_qty - sol.qty_transferred
                        if qty > current_qty_demand:
                            self._add_qty_to_intermediate_delivery(
                                dict_moves_per_picking, line, qty
                            )
                        elif qty < current_qty_demand:
                            self._remove_qty_from_intermediate_delivery(
                                dict_moves_per_picking,
                                sol.fsm_trace_id,
                                qty - current_qty_demand,
                            )
                    else:  # the sn/lot id was changed
                        # adds the qty of the new trace_id
                        self._add_qty_to_intermediate_delivery(
                            dict_moves_per_picking, line, qty
                        )
                        # removes the qty of the old trace_id
                        self._remove_qty_from_intermediate_delivery(
                            dict_moves_per_picking,
                            sol.fsm_trace_id,
                            0 - (sol.product_qty - sol.qty_transferred),
                        )
                if (
                    sol.fsm_trace_id != line.trace_id
                ):  # update the trace_id of the deliveries linked to the sale_order_line
                    self._update_lot_id(sol, line)
                vals = {
                    "fsm_trace_id": line.trace_id,
                    "product_qty": qty + line.sale_order_line_id.qty_transferred,
                }
                if self.task_id.under_warranty:
                    vals["price_unit"] = 0
                line.sale_order_line_id.with_context(
                    industry_fsm_stock_tracking=True
                ).write(vals)
