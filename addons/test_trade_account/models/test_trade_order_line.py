from dataclasses import replace

from odoo import api, fields, models

from odoo.addons.trade.tools import SALE


class TestTradeOrderLine(models.Model):
    _name = "test_trade.order.line"
    _inherit = ["test_trade.order.line", "mixin.order.line.invoice"]

    invoice_line_ids = fields.Many2many(
        relation="account_move_line_test_trade_order_line_rel",
        column1="order_line_id",
        column2="move_line_id",
    )

    _direction = replace(SALE, invoice_policy_field="test_trade_order_invoice_policy")

    qty_invoiced_input = fields.Float(digits="Product Unit")
    qty_invoiced_draft_input = fields.Float(digits="Product Unit")

    @api.depends(
        "product_qty", "price_unit", "qty_invoiced_input", "qty_invoiced_draft_input"
    )
    def _compute_invoice_amounts(self):
        for line in self:
            if line.display_type:
                line.qty_invoiced = 0.0
                line.qty_invoiced_draft = 0.0
                line.qty_to_invoice = 0.0
                line.amount_taxexc_invoiced = 0.0
                line.amount_taxinc_invoiced = 0.0
                line.amount_taxexc_invoiced_draft = 0.0
                line.amount_taxinc_invoiced_draft = 0.0
                line.amount_taxexc_to_invoice = 0.0
                line.amount_taxinc_to_invoice = 0.0
                continue
            price = line.price_unit or 0.0
            line.qty_invoiced = line.qty_invoiced_input
            line.qty_invoiced_draft = line.qty_invoiced_draft_input
            line.qty_to_invoice = (
                (line.product_qty or 0.0) - line.qty_invoiced - line.qty_invoiced_draft
            )
            line.amount_taxexc_invoiced = line.qty_invoiced * price
            line.amount_taxinc_invoiced = line.amount_taxexc_invoiced
            line.amount_taxexc_invoiced_draft = line.qty_invoiced_draft * price
            line.amount_taxinc_invoiced_draft = line.amount_taxexc_invoiced_draft
            line.amount_taxexc_to_invoice = line.qty_to_invoice * price
            line.amount_taxinc_to_invoice = line.amount_taxexc_to_invoice

    @api.depends(
        "qty_to_invoice",
        "qty_invoiced",
        "qty_invoiced_draft",
        "product_qty",
        "qty_transferred",
        "is_downpayment",
        "amount_taxexc_to_invoice",
        "product_id.test_trade_order_invoice_policy",
    )
    def _compute_invoice_state(self):
        return super()._compute_invoice_state()

    def _get_invoice_line_link_field(self):
        return "test_trade_order_line_ids"
