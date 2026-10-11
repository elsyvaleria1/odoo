from odoo import api, fields, models


class PosOrder(models.Model):
    _inherit = "pos.order"

    customer_due_total = fields.Monetary(
        string="Due",
        currency_field="currency_id",
        compute="_compute_customer_due_total",
        store=True,
    )
    init_customer_due_total = fields.Monetary(
        string="Initial due (before any settlement)",
        currency_field="currency_id",
    )
    settled_order_line_ids = fields.One2many(
        comodel_name="pos.order.line",
        inverse_name="settled_order_id",
        string="Settled Order Lines",
    )
    settled_orders_count = fields.Count(
        count_of="settled_order_line_ids",
        string="Number of settled orders",
        store=True,
    )
    commercial_partner_id = fields.Many2one(
        comodel_name="res.partner",
        related="partner_id.commercial_partner_id",
        readonly=True,
    )

    @api.model
    def _load_pos_data_fields(self, config):
        return super()._load_pos_data_fields(config) + [
            "customer_due_total",
            "init_customer_due_total",
            "settled_order_line_ids",
            "settled_orders_count",
            "commercial_partner_id",
        ]

    @api.depends("payment_ids", "settled_order_line_ids", "is_invoiced")
    def _compute_customer_due_total(self) -> None:
        for order in self:
            order_pay_later_pm = order.payment_ids.filtered(
                lambda payment: (
                    payment.amount > 0 and payment.payment_method_id.type == "pay_later"
                )
            )
            if order.partner_id and order_pay_later_pm and not order.is_invoiced:
                if order.customer_due_total:
                    order_due = order.init_customer_due_total
                    order_settled = self.env.company.currency_id.round(
                        sum(order.settled_order_line_ids.mapped("price_unit"))
                    )
                    order.customer_due_total = order_due - order_settled
                else:
                    order_due = sum(
                        order.payment_ids.filtered(
                            lambda payment: (
                                payment.amount > 0
                                and payment.payment_method_id.type == "pay_later"
                            )
                        ).mapped("amount")
                    )
                    customer_due = order.partner_id.get_total_due(order.config_id.id)[
                        "res.partner"
                    ][0]["total_due"]
                    total_before = customer_due - order_due
                    if customer_due > 0:
                        if total_before < 0:
                            order_due = customer_due
                        if order_due > 0:
                            order.customer_due_total = order_due
                            order.init_customer_due_total = order_due
            else:
                order.customer_due_total = 0

    def action_view_settled_orders(self) -> dict:
        return {
            "name": self.env._("Settled Orders"),
            "view_mode": "list,form",
            "res_model": "pos.order",
            "type": "ir.actions.act_window",
            "domain": [
                ("id", "in", self.mapped("settled_order_line_ids.order_id").ids)
            ],
        }

    def _get_payments(self):
        payments = super()._get_payments()
        payments += (
            self.settled_order_line_ids.order_id.payment_ids.sudo().with_company(
                self.company_id
            )
        )
        return payments
