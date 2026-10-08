from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class AccountMove(models.Model):
    _name = "account.move"
    _inherit = ["account.move", "mixin.pos.load"]

    pos_order_ids = fields.One2many(
        comodel_name="pos.order",
        inverse_name="account_move",
    )
    pos_payment_ids = fields.One2many(
        comodel_name="pos.payment",
        inverse_name="account_move_id",
    )
    pos_refunded_invoice_ids = fields.Many2many(
        comodel_name="account.move",
        relation="refunded_invoices",
        column1="refund_account_move",
        column2="original_account_move",
    )
    reversed_pos_order_id = fields.Many2one(
        comodel_name="pos.order",
        string="Reversed POS Order",
        index="btree_not_null",
        help="The pos order that was reverted after closing the session to create an invoice for it.",
    )
    pos_diff_session_id = fields.Many2one(
        comodel_name="pos.session",
        string="POS Closing Difference",
        index="btree_not_null",
        help="Session whose closing produced this payment-method difference entry.",
    )
    pos_diff_payment_method_id = fields.Many2one(
        comodel_name="pos.payment.method",
        string="POS Closing Difference Payment Method",
        index="btree_not_null",
        copy=False,
        help="Payment method whose closing count produced this difference entry.",
    )
    pos_session_ids = fields.One2many(
        comodel_name="pos.session",
        inverse_name="move_id",
        string="POS Sessions",
    )
    pos_order_count = fields.Integer(
        string="POS Order Count",
        compute="_compute_pos_order_count",
    )

    @api.depends("pos_order_ids")
    def _compute_pos_order_count(self) -> None:
        for move in self:
            move.pos_order_count = len(move.sudo().pos_order_ids)

    @api.depends("tax_cash_basis_created_move_ids", "pos_session_ids")
    def _compute_always_tax_exigible(self) -> None:
        super()._compute_always_tax_exigible()
        for move in self:
            if move.always_tax_exigible or move.tax_cash_basis_created_move_ids:
                continue
            if move.pos_session_ids:
                move.always_tax_exigible = True

    def _stock_account_get_last_step_stock_moves(self):
        stock_moves = super()._stock_account_get_last_step_stock_moves()
        for invoice in self.filtered(lambda x: x.move_type == "out_invoice"):
            stock_moves += (
                invoice.sudo()
                .mapped("pos_order_ids.picking_ids.move_ids")
                .filtered(
                    lambda x: (
                        x.state == "done" and x.location_dest_id.usage == "customer"
                    )
                )
            )
        for invoice in self.filtered(lambda x: x.move_type == "out_refund"):
            stock_moves += (
                invoice.sudo()
                .mapped("pos_order_ids.picking_ids.move_ids")
                .filtered(
                    lambda x: x.state == "done" and x.location_id.usage == "customer"
                )
            )
        return stock_moves

    def _prepare_invoice_lot_rows(self):
        self.check_singleton()

        lot_values = super()._prepare_invoice_lot_rows()

        if self.state == "draft":
            return lot_values

        for order in self.sudo().pos_order_ids:
            for line in order.lines:
                lots = line.pack_lot_ids or False
                if lots:
                    for lot in lots:
                        lot_values.append(
                            {
                                "product_name": lot.product_id.name,
                                "quantity": line.qty
                                if lot.product_id.tracking == "lot"
                                else 1.0,
                                "uom_name": line.product_uom_id.name,
                                "lot_name": lot.lot_name,
                                "pos_lot_id": lot.id,
                            }
                        )

        return lot_values

    def _compute_invoice_payments_widget(self) -> None:
        super()._compute_invoice_payments_widget()
        for move in self:
            if (
                not move.invoice_payments_widget
                or move.state != "posted"
                or not move.is_invoice(include_receipts=True)
            ):
                continue
            content = move.invoice_payments_widget["content"]
            counterparts = (
                self.env["account.move"]
                .sudo()
                .browse([row["move_id"] for row in content])
            )
            for row, counterpart in zip(content, counterparts, strict=True):
                row["pos_payment_name"] = counterpart.pos_payment_ids[
                    :1
                ].payment_method_id.name

    def _compute_amounts(self) -> None:
        super()._compute_amounts()
        for move in self:
            if move.move_type == "entry" and move.reversed_pos_order_id:
                move.amount_total_signed *= -1

    def _compute_is_storno(self) -> None:
        super()._compute_is_storno()
        for move in self:
            move.is_storno = move.is_storno or (
                move.company_id.account_config_id.account_storno
                and move.reversed_pos_order_id
            )

    def action_view_source_pos_orders(self):
        self.check_singleton()
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "point_of_sale.action_pos_pos_form"
        )

        if len(self.pos_order_ids) == 1:
            action["views"] = [
                (self.env.ref("point_of_sale.view_pos_pos_form", False).id, "form")
            ]
            action["res_id"] = self.pos_order_ids.id
        else:
            action["domain"] = [("id", "in", self.pos_order_ids.ids)]
        return action

    def action_draft(self):
        if self.sudo().pos_order_ids.filtered(lambda o: o.session_id.state != "closed"):
            _debug.logic("reset_to_draft_refused_session_open", moves=self)
            self.env.user._bus_send(
                "simple_notification",
                {
                    "type": "danger",
                    "message": self.env._(
                        "You can't reset this invoice to draft because the POS session is still open. Please close the ongoing session first, then try again."
                    ),
                    "sticky": True,
                },
            )
            return False
        return super().action_draft()

    @api.model
    def _load_pos_data_fields(self, config):
        result = super()._load_pos_data_fields(config)
        return result or ["id", "name"]

    @api.model
    def _load_pos_data_domain(self, data, config):
        return False


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def _get_cogs_value(self):
        self.check_singleton()
        if not self.product_id:
            return self.price_unit
        price_unit = super()._get_cogs_value()
        sudo_order = self.move_id.sudo().pos_order_ids
        if sudo_order:
            pos_price_unit = sudo_order._get_pos_anglo_saxon_price_unit(
                self.product_id, self.quantity
            )
            _debug.logic(
                "cogs_price_unit",
                orders=sudo_order,
                product=self.product_id,
                pos_price_unit=pos_price_unit,
                account_price_unit=price_unit,
            )
            if not self.product_id.sudo().cost_currency_id.is_zero(pos_price_unit):
                price_unit = pos_price_unit
        return price_unit

    def _compute_name(self):
        amls = self.filtered(lambda l: not l.move_id.pos_session_ids)
        super(AccountMoveLine, amls)._compute_name()
