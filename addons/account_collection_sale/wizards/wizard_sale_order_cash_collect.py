from odoo import api, fields, models


class WizardSaleOrderCashCollect(models.TransientModel):
    _name = "wizard.sale.order.cash.collect"
    _description = "Collect a Cash Sale"

    order_id = fields.Many2one(
        comodel_name="sale.order",
        readonly=True,
        required=True,
    )
    currency_id = fields.Many2one(
        related="order_id.currency_id",
    )
    amount = fields.Monetary(
        currency_field="currency_id",
        compute="_compute_amount",
        precompute=True,
        store=True,
        readonly=False,
        required=True,
        help="What the customer paid you.",
    )
    date = fields.Date(
        string="Paid On",
        default=fields.Date.context_today,
        required=True,
    )
    hand_over = fields.Boolean(
        string="The Customer Takes the Goods Now",
        help="Deliver the order now, from where its goods are at hand: the "
        "salesperson's vehicle, or the warehouse when the customer picks it up.",
    )
    collection_method = fields.Selection(
        selection=[("cash", "Cash"), ("check", "Check")],
        string="Paid In",
        default="cash",
        required=True,
    )

    @api.depends("order_id")
    def _compute_amount(self) -> None:
        for wizard in self:
            wizard.amount = wizard.order_id.amount_total

    def action_collect(self):
        self.check_singleton()
        payment = self.order_id.with_privilege(
            "account_collection.privilege_register_collection",
            "account_collection_sale.privilege_invoice_cash_sale",
            "account_collection_sale.privilege_hand_over_cash_sale",
            reason="a collector invoices, collects and hands over a cash sale on the spot",
        )._settle_cash_sale(
            self.amount,
            self.date,
            self.collection_method,
            self.env.user,
            hand_over=self.hand_over,
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.payment",
            "res_id": payment.id,
            "view_mode": "form",
            "views": [(False, "form")],
        }
