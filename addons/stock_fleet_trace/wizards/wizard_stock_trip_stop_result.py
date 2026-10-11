from odoo import Command, api, fields, models
from odoo.exceptions import UserError


class WizardStockTripStopResult(models.TransientModel):
    """What the customer took at a stop, product by product and lot by lot."""

    _name = "wizard.stock.trip.stop.result"
    _description = "Trip Stop Result"

    picking_id = fields.Many2one(
        comodel_name="stock.picking",
        required=True,
        ondelete="cascade",
    )
    batch_id = fields.Many2one(related="picking_id.batch_id")
    line_ids = fields.One2many(
        comodel_name="wizard.stock.trip.stop.result.line",
        inverse_name="wizard_id",
    )
    reason_id = fields.Many2one(
        comodel_name="stock.picking.unbatch.reason",
        string="Reason Nothing Was Delivered",
        domain="[('moment', 'in', ('on_route', 'any')), "
        "('scope', 'in', ('transfer', 'both'))]",
        help="Required when the customer took nothing.",
    )
    note = fields.Text()

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        picking = self.env["stock.picking"].browse(res.get("picking_id"))
        if picking and "line_ids" in fields_list:
            scanned = picking._trip_scanned_by_lot() if picking.trip_scan_ids else None
            lines = []
            for line in picking.move_ids.move_line_ids:
                if line.state in ("done", "cancel"):
                    continue
                delivered = line.quantity
                if scanned is not None:
                    key = (line.product_id, line.trace_id)
                    delivered = min(line.quantity, scanned.get(key, 0.0))
                    scanned[key] = scanned.get(key, 0.0) - delivered
                lines.append(
                    Command.create(
                        {
                            "move_line_id": line.id,
                            "qty_on_board": line.quantity,
                            "qty_delivered": delivered,
                        }
                    )
                )
            res["line_ids"] = lines
        return res

    def _delivers_something(self) -> bool:
        return any(line.qty_delivered for line in self.line_ids)

    def _check_ready(self) -> None:
        self.check_singleton()
        picking = self.picking_id
        if not picking.batch_id.date_departure:
            raise UserError(
                self.env._(
                    "Transfer %s is not on a trip that has departed.", picking.name
                )
            )
        if picking.state != "assigned":
            raise UserError(
                self.env._("Transfer %s is not ready to deliver.", picking.name)
            )
        for line in self.line_ids:
            if line.qty_delivered < 0 or line.qty_delivered > line.qty_on_board:
                raise UserError(
                    self.env._(
                        "%(product)s: the quantity delivered must be between 0 and "
                        "what the vehicle carries (%(qty)s).",
                        product=line.product_id.display_name,
                        qty=line.qty_on_board,
                    )
                )
            if line.qty_rejected and not line.reason_id and self._delivers_something():
                raise UserError(
                    self.env._(
                        "%s: say why the customer did not take it.",
                        line.product_id.display_name,
                    )
                )

    def action_confirm(self):
        self.check_singleton()
        self._check_ready()
        picking = self.picking_id
        batch = picking.batch_id
        picking.trip_partial_review = False
        if not self._delivers_something():
            if not self.reason_id:
                raise UserError(
                    self.env._(
                        "The customer took nothing: give the reason for the delivery."
                    )
                )
            picking.delivery_failure_reason_id = self.reason_id
            reason = self.reason_id.name
            if self.note:
                reason = f"{reason}: {self.note}"
            picking._register_delivery_failure(reason)
            return {"type": "ir.actions.act_window_close"}

        wants_backorder = False
        rejected = self.line_ids.filtered("qty_rejected")
        for line in self.line_ids:
            line.move_line_id.quantity = line.qty_delivered
        for move in picking.move_ids.filtered(
            lambda m: m.state not in ("done", "cancel")
        ):
            move.picked = True
            dropped = sum(
                line.qty_rejected
                for line in rejected
                if line.move_line_id.move_id == move
                and not line.reason_id.creates_backorder
            )
            if dropped:
                move.product_uom_qty = max(move.product_uom_qty - dropped, 0.0)
            if move.product_uom_qty > move.quantity:
                wants_backorder = True
        result = "complete" if not rejected and not wants_backorder else "partial"
        picking.with_context(trip_delivery_result=result).button_validate(
            skip_backorder=True,
            cancel_backorder_ids=() if wants_backorder else picking.ids,
        )
        if wants_backorder:
            self._release_backorders()
        for line in rejected:
            batch._trip_checkpoint(
                "rejection",
                picking_id=picking.id,
                product_id=line.product_id.id,
                trace_id=line.trace_id.id,
                quantity=line.qty_rejected,
                reason_id=line.reason_id.id,
                note=line.note or False,
            )
        if rejected:
            self._notify_sales(rejected)
        return {"type": "ir.actions.act_window_close"}

    def _release_backorders(self) -> None:
        picking = self.picking_id
        backorders = picking.backorder_ids.filtered(
            lambda p: p.state not in ("done", "cancel")
        )
        if not backorders:
            return
        for move in backorders.move_ids:
            legs = move.move_orig_ids.filtered(lambda m: m.trip_move_kind == "load")
            if legs:
                move._unreserve()
                move.move_orig_ids = [
                    Command.set((move.move_orig_ids - legs | legs.move_orig_ids).ids)
                ]
        batch = picking.batch_id
        for backorder in backorders:
            backorder.activity_schedule(
                "mail.mail_activity_data_todo",
                user_id=(batch.supervisor_id or self.env.user).id,
                summary=self.env._("Stage the goods for %s again", backorder.name),
                note=self.env._(
                    "Left pending on trip %(batch)s: the customer still expects it.",
                    batch=batch.name,
                ),
            )

    def _notify_sales(self, rejected) -> None:
        picking = self.picking_id
        order = picking.with_privilege(
            "stock_fleet_trace.privilege_trip_trace_record",
            reason="a stop tells the salesperson about invoiced goods refused",
        ).sale_id
        if not order:
            return
        invoiced = {
            line.product_id
            for line in order.line_ids
            if line.qty_invoiced or line.qty_invoiced_draft
        }
        refused = rejected.filtered(lambda line: line.product_id in invoiced)
        if not refused:
            return
        lines = "\n".join(
            f"- {line.product_id.display_name}: {line.qty_rejected} "
            f"({line.reason_id.name})"
            for line in refused
        )
        picking.activity_schedule(
            "mail.mail_activity_data_todo",
            user_id=(order.user_id or self.env.user).id,
            summary=self.env._("Invoiced goods rejected on delivery"),
            note=self.env._(
                "%(picking)s (%(order)s) came back partly rejected by the customer. "
                "Decide on a credit note or a new delivery:\n%(lines)s",
                picking=picking.name,
                order=order.name,
                lines=lines,
            ),
        )


class WizardStockTripStopResultLine(models.TransientModel):
    _name = "wizard.stock.trip.stop.result.line"
    _description = "Trip Stop Result Line"

    wizard_id = fields.Many2one(
        comodel_name="wizard.stock.trip.stop.result",
        required=True,
        ondelete="cascade",
    )
    move_line_id = fields.Many2one(
        comodel_name="stock.move.line",
        required=True,
        ondelete="cascade",
    )
    product_id = fields.Many2one(related="move_line_id.product_id")
    trace_id = fields.Many2one(related="move_line_id.trace_id")
    uom_id = fields.Many2one(related="move_line_id.product_uom_id")
    qty_on_board = fields.Float(
        string="On Board",
        digits="Product Unit",
    )
    qty_delivered = fields.Float(
        string="Delivered",
        digits="Product Unit",
    )
    qty_rejected = fields.Float(
        string="Not Taken",
        digits="Product Unit",
        compute="_compute_qty_rejected",
    )
    reason_id = fields.Many2one(
        comodel_name="stock.picking.unbatch.reason",
        string="Reason",
        domain="[('scope', 'in', ('line', 'both'))]",
    )
    note = fields.Char()

    @api.depends("qty_on_board", "qty_delivered")
    def _compute_qty_rejected(self) -> None:
        for line in self:
            line.qty_rejected = max(line.qty_on_board - line.qty_delivered, 0.0)


class WizardStockPickingUnbatchUndelivered(models.TransientModel):
    _inherit = "wizard.stock.picking.unbatch.undelivered"

    reason_id = fields.Many2one(
        domain="[('moment', 'in', ('on_route', 'any')), "
        "('scope', 'in', ('transfer', 'both'))]",
    )
