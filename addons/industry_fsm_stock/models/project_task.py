from odoo import fields, models
from odoo.libs.debug_log import DebugLog
from odoo.tools import float_compare, float_round

_debug = DebugLog(__name__)


class ProjectTask(models.Model):
    _name = "project.task"
    _inherit = "project.task"

    stock_move_customer_product_count = fields.Integer(
        compute="_compute_stock_move_customer_product_total"
    )

    def _deliver_materials(self) -> None:
        _debug.pipeline("fsm_materials_deliver", tasks=self)
        for task in self.filtered(lambda x: x.allow_billable and x.sale_order_id):
            exception = False
            sale_line = (
                self.env["sale.order.line"]
                .sudo()
                .search(
                    [
                        ("order_id", "=", task.sale_order_id.id),
                        ("task_id", "=", task.id),
                    ]
                )
            )
            for order_line in sale_line:
                to_log = {}
                total_qty = sum(
                    order_line.move_ids.filtered(
                        lambda m: m.state != "cancel" and not m.move_dest_ids
                    ).mapped("product_uom_qty")
                )
                if (
                    float_compare(
                        order_line.product_qty,
                        total_qty,
                        precision_rounding=order_line.product_uom_id.rounding,
                    )
                    < 0
                    and order_line.product_id in order_line.move_ids.product_id
                ):
                    to_log[order_line] = (order_line.product_qty, total_qty)

                if to_log:
                    exception = True
                    documents = self.env[
                        "mixin.stock.activity"
                    ]._get_log_activity_documents(to_log, "move_ids", "UP")
                    documents = {
                        k: v
                        for k, v in documents.items()
                        if k[0].state not in ["cancel", "done"]
                    }
                    self.env["sale.order"]._log_decrease_ordered_quantity(documents)
            if not exception:
                task.sudo()._mark_stock_moves_done()

    def _mark_stock_moves_done(self, done_picking_ids=None) -> None:
        _debug.pipeline("fsm_moves_mark_done", tasks=self)
        self.check_singleton()
        if not done_picking_ids:
            done_picking_ids = set()
        all_fsm_sn_moves = self.env["stock.move"]
        ml_to_create = []
        for so_line in self.sale_order_id.line_ids:
            if not (
                so_line.task_id.is_fsm
                or so_line.project_id.is_fsm
                or so_line.fsm_trace_id
            ):
                continue
            qty = so_line.product_qty - so_line.qty_transferred
            fsm_sn_moves = self.env["stock.move"]
            if not qty:
                continue
            for move in so_line.move_ids:
                if move.state in ["done", "cancel"] or (
                    move.quantity >= qty and move.picked
                ):
                    continue
                fsm_sn_moves |= move
                while move.move_orig_ids.filtered_domain(
                    ["|", ("picked", "=", False), ("quantity", "<", qty)]
                ):
                    move = move.move_orig_ids
                    fsm_sn_moves |= move
            for fsm_sn_move in fsm_sn_moves:
                ml_vals = False
                if not fsm_sn_move.move_line_ids:
                    ml_vals = fsm_sn_move._prepare_move_line_vals(quantity=0)
                    ml_vals["quantity"] = fsm_sn_move.product_uom_qty
                    ml_vals["trace_id"] = so_line.fsm_trace_id.id
                    ml_to_create.append(ml_vals)
                else:
                    qty_done = 0
                    fsm_sn_move.move_line_ids.trace_id = so_line.fsm_trace_id
                    for move_line in fsm_sn_move.move_line_ids:
                        qty_done += move_line.quantity
                    missing_qty = fsm_sn_move.product_uom_qty - qty_done
                    if missing_qty > 0:
                        ml_vals = fsm_sn_move._prepare_move_line_vals(quantity=0)
                        ml_vals["quantity"] = missing_qty
                        ml_vals["trace_id"] = so_line.fsm_trace_id.id
                        ml_to_create.append(ml_vals)
                if ml_vals:
                    quants = self.env["stock.quant"]._gather(
                        fsm_sn_move.product_id,
                        fsm_sn_move.location_id,
                        trace_id=so_line.fsm_trace_id,
                    )
                    if fsm_sn_move.product_id.tracking == "serial":
                        quants = quants.filtered(
                            lambda q: q.product_uom_id.compare(q.quantity, 1) == 0
                        )
                    ml_vals["location_id"] = (
                        quants[:1].location_id.id or fsm_sn_move.location_id.id
                    )
            all_fsm_sn_moves |= fsm_sn_moves
        self.env["stock.move.line"].create(ml_to_create)
        for so_line in self.sale_order_id.line_ids:
            if so_line.task_id == self and so_line.product_id.service_policy not in [
                "delivered_timesheet",
                "delivered_milestones",
            ]:
                so_line.qty_transferred = so_line.product_qty

        def is_fsm_material_picking(picking, task) -> bool:
            moves = picking.move_ids
            while moves.move_dest_ids:
                moves = moves.move_dest_ids
            for move in moves:
                sol = move.sale_line_id
                if sol.fsm_trace_id:
                    continue
                if not (
                    sol.product_id != task.project_id.timesheet_product_id
                    and sol != task.sale_line_id
                    and (sol.task_id == task or sol.task_id.fsm_done)
                ):
                    return False
            return True

        pickings_to_do = self.sale_order_id.picking_ids.filtered(
            lambda p: (
                p.state not in ["done", "cancel"] and is_fsm_material_picking(p, self)
            )
        )
        for move in pickings_to_do.move_ids:
            if move.state in ("done", "cancel") or move in all_fsm_sn_moves:
                continue
            rounding = move.product_uom_id.rounding
            if (
                float_compare(
                    move.quantity, move.product_uom_qty, precision_rounding=rounding
                )
                < 0
            ):
                qty_to_do = float_round(
                    move.product_uom_qty - move.quantity,
                    precision_rounding=rounding,
                    rounding_method="HALF-UP",
                )
                move.quantity = qty_to_do
        pickings_to_do.with_context(skip_sms=True).button_validate()

        done_picking_ids.update(pickings_to_do.ids)
        remaining_to_do = self.sale_order_id.picking_ids.filtered(
            lambda p: (
                p.state not in ["done", "cancel"] and is_fsm_material_picking(p, self)
            )
        )
        if any(
            remaining_id not in done_picking_ids for remaining_id in remaining_to_do.ids
        ):
            self._mark_stock_moves_done(done_picking_ids=done_picking_ids)

    def _get_task_SOL_stock_move_customer(self):
        return self.env["stock.move"].search(
            [
                ("sale_line_id.order_id", "=", self.sale_order_id.id),
                ("sale_line_id.task_id", "=", False),
                ("state", "not in", ["done", "cancel"]),
                ("location_dest_usage", "=", "customer"),
            ]
        )

    def _compute_stock_move_customer_product_total(self) -> None:
        for record in self:
            customer_move_lines = record.sudo()._get_task_SOL_stock_move_customer()
            record.stock_move_customer_product_count = round(
                sum(customer_move_lines.mapped("product_uom_qty"))
            )

    def action_fsm_pick_up(self) -> dict:
        _debug.lifecycle("fsm_task_pick_up", tasks=self)
        stock_move_ids = self.sudo()._get_task_SOL_stock_move_customer()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Pick Up Material"),
            "view_mode": "list,kanban",
            "mobile_view_mode": "kanban",
            "domain": [("id", "in", stock_move_ids.ids)],
            "res_model": "stock.move",
            "views": [
                (
                    self.env.ref(
                        "industry_fsm_stock.view_move_tree_picking_redirect"
                    ).id,
                    "list",
                ),
                (
                    self.env.ref(
                        "industry_fsm_stock.view_move_kanban_picking_redirect"
                    ).id,
                    "kanban",
                ),
            ],
        }

    def _fsm_get_or_create_sale_order(self):
        _debug.logic("fsm_sale_order_ensure", tasks=self)
        sale_order = super()._fsm_get_or_create_sale_order()
        if sale_order.state == "draft":
            sale_order.with_context(fsm_create_sale_order=True).action_confirm()
        return sale_order

    def _fsm_create_sale_order(self) -> None:
        _debug.lifecycle("fsm_sale_order_create", tasks=self)
        super()._fsm_create_sale_order()
        sale_order = self.sale_order_id
        if self.env.user.has_group("project.group_project_user"):
            sale_order = self.sale_order_id.sudo()
        sale_order.with_context(fsm_create_sale_order=True).action_confirm()

    def action_fsm_view_material(self):
        action = super().action_fsm_view_material()
        action["context"].update(
            {"warehouse_id": self.env.user._get_default_warehouse_id().id}
        )
        return action

    def action_fsm_validate(self, stop_running_timers=False):
        _debug.pipeline("fsm_task_validate", tasks=self)
        res = super().action_fsm_validate(stop_running_timers)
        if res is True:
            self.sudo().sale_order_id.filtered(
                lambda so: so._is_lock_required()
            ).action_lock()
        return res
