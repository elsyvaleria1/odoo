from odoo import Command, api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardStockPickingReturn(models.TransientModel):
    _name = "wizard.stock.picking.return"
    _description = "Return Picking"

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        if (
            self.env.context.get("active_id")
            and self.env.context.get("active_model") == "stock.picking"
        ):
            if len(self.env.context.get("active_ids", [])) > 1:
                raise UserError(
                    self.env._("You may only return one picking at a time.")
                )
            picking = self.env["stock.picking"].browse(
                self.env.context.get("active_id")
            )
            if picking.exists():
                res.update({"picking_id": picking.id})
        return res

    picking_id = fields.Many2one(comodel_name="stock.picking")
    picking_type_code = fields.Selection(
        related="picking_id.picking_type_code",
        readonly=True,
    )
    product_return_moves = fields.One2many(
        comodel_name="wizard.stock.picking.return.line",
        inverse_name="wizard_id",
        string="Moves",
        compute="_compute_product_return_moves",
        precompute=True,
        store=True,
        readonly=False,
    )
    company_id = fields.Many2one(related="picking_id.company_id")

    @api.depends("picking_id")
    def _compute_product_return_moves(self) -> None:
        for wizard in self:
            if not wizard.picking_id:
                wizard.product_return_moves = [Command.clear()]
                continue
            product_return_moves = [Command.clear()]
            if not wizard.picking_id._can_return():
                raise UserError(self.env._("You may only return Done pickings."))
            line_fields = list(self.env["wizard.stock.picking.return.line"]._fields)
            product_return_moves_data_tmpl = self.env[
                "wizard.stock.picking.return.line"
            ].default_get(line_fields)
            for move in wizard.picking_id.move_ids:
                if move.state == "cancel":
                    continue
                if move.location_dest_usage == "inventory":
                    continue
                product_return_moves_data = dict(product_return_moves_data_tmpl)
                product_return_moves_data.update(
                    wizard._prepare_stock_return_picking_line_vals_from_move(move)
                )
                product_return_moves.append(Command.create(product_return_moves_data))
            if len(product_return_moves) == 1:
                raise UserError(
                    self.env._(
                        "No products to return (only lines in Done state and not fully returned yet can be returned)."
                    )
                )
            wizard.product_return_moves = product_return_moves

    @api.model
    def _prepare_stock_return_picking_line_vals_from_move(self, stock_move) -> dict:
        return {
            "product_id": stock_move.product_id.id,
            "quantity": 0,
            "move_id": stock_move.id,
        }

    def _prepare_picking_default_values(self):
        return self._prepare_picking_default_values_based_on(self.picking_id)

    def _prepare_picking_default_values_based_on(self, picking) -> dict:
        location = picking.location_dest_id
        return_type = picking.picking_type_id.return_picking_type_id
        if return_type and return_type.code == "incoming":
            location_dest = return_type.default_location_dest_id
        else:
            location_dest = picking.location_id

        return {
            "move_ids": [],
            "picking_type_id": return_type.id or picking.picking_type_id.id,
            "state": "draft",
            "return_id": picking.id,
            "origin": self.env._(
                "Return of %(picking_name)s", picking_name=picking.name
            ),
            "location_id": location.id,
            "location_dest_id": location_dest.id,
        }

    @_debug.perf.timed
    def _create_return(self):
        _debug.pipeline(
            "create_return",
            picking=self.picking_id.id,
            lines=len(self.product_return_moves),
        )
        downstream = self.env["stock.move"]
        if self.picking_id:
            downstream = self.product_return_moves.filtered(
                lambda line: not line.uom_id.is_zero(line.quantity)
            ).move_id.move_dest_ids.filtered(
                lambda m: m.state not in ("done", "cancel")
            )
            downstream._unreserve()

            new_picking = self.picking_id.copy(self._prepare_picking_default_values())
            new_picking.user_id = False
            new_picking.message_post_with_source(
                "mail.message_origin_link",
                render_values={"self": new_picking, "origin": self.picking_id},
                subtype_xmlid="mail.mt_note",
            )
        else:
            new_picking = self.env["stock.picking"].create(
                self._prepare_picking_default_values()
            )

        returned_lines = False
        for return_line in self.product_return_moves:
            if return_line._process_line(new_picking):
                returned_lines = True
        if not returned_lines:
            raise UserError(
                self.env._("Please specify at least one non-zero quantity.")
            )

        _debug.pipeline("return_confirm_assign", picking=new_picking.id)
        new_picking.action_confirm()
        new_picking.action_assign()
        downstream._action_assign()
        return new_picking

    @_debug.perf.timed
    def _create_exchange(self, return_picking):
        exchange_picking = return_picking.copy(
            self._prepare_picking_default_values_based_on(return_picking)
        )
        _debug.pipeline(
            "exchange_created",
            return_picking=return_picking.id,
            exchange_picking=exchange_picking.id,
        )
        exchange_picking.user_id = False
        exchange_picking.message_post_with_source(
            "mail.message_origin_link",
            render_values={"self": exchange_picking, "origin": return_picking},
            subtype_xmlid="mail.mt_note",
        )
        for return_line in self.product_return_moves:
            return_line._process_line(exchange_picking)

        exchange_picking.move_ids.write(
            {
                "origin_returned_move_id": False,
                "move_orig_ids": False,
            }
        )
        exchange_picking.action_confirm()
        exchange_picking.action_assign()
        return exchange_picking

    def action_create_returns(self) -> dict:
        self.check_singleton()
        new_picking = self._create_return()
        return {
            "name": self.env._("Returned Picking"),
            "view_mode": "form",
            "res_model": "stock.picking",
            "res_id": new_picking.id,
            "type": "ir.actions.act_window",
            "context": self.env.context,
        }

    def action_create_returns_all(self):
        self.check_singleton()
        for return_line in self.product_return_moves.filtered("move_id"):
            return_line.quantity = return_line._get_returnable_quantity()
            _debug.logic(
                "returnable_quantity",
                move=return_line.move_id.id,
                quantity=return_line.quantity,
            )
        if all(
            line.uom_id.is_zero(line.quantity) for line in self.product_return_moves
        ):
            raise UserError(
                self.env._("Everything this transfer moved has already been returned.")
            )
        return self.action_create_returns()

    def action_create_exchanges(self):
        action = self.action_create_returns()
        if self.picking_id.picking_type_id.code == "incoming":
            return_picking = self.env["stock.picking"].browse([action["res_id"]])
            self._create_exchange(return_picking)
            return action

        proc_list = []
        for line in self.product_return_moves:
            if not line.move_id:
                continue
            proc_values = self._prepare_procurement_vals(line)
            proc_list.append(
                self.env["stock.rule"].Procurement(
                    line.product_id,
                    line.quantity,
                    line.uom_id,
                    line.move_id.location_dest_id or self.picking_id.location_dest_id,
                    line.product_id.display_name,
                    self.picking_id.origin,
                    self.picking_id.company_id,
                    proc_values,
                )
            )
        if proc_list:
            _debug.pipeline("exchange_procurements", procurements=len(proc_list))
            self.env["stock.rule"].run(proc_list)
        return action

    def _prepare_procurement_vals(self, line):
        self.check_singleton()
        return {
            "reference_ids": self.picking_id.reference_ids,
            "date_planned": line.move_id.date or fields.Datetime.now(),
            "warehouse_id": self.picking_id.picking_type_id.warehouse_id,
            "partner_id": self.picking_id.partner_id.id,
            "location_final_id": line.move_id.location_final_id
            or self.picking_id.location_dest_id,
            "company_id": self.picking_id.company_id,
        }
