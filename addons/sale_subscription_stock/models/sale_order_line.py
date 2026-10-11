from typing import Self

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog
from odoo.tools import clean_context, format_date

from odoo.addons.sale_subscription.models.sale_order import SUBSCRIPTION_PROGRESS_STATE

_debug = DebugLog(__name__)


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"


    @api.depends("order_id.next_invoice_date", "order_id.start_date")
    def _compute_qty_transferred(self):
        return super()._compute_qty_transferred()


    def _get_stock_moves_outgoing_incoming(self):
        outgoing_moves, incoming_moves = super()._get_stock_moves_outgoing_incoming()
        if not self._filtered_stock_subscription_lines():
            return outgoing_moves, incoming_moves
        order = self.order_id
        period_start = order.last_invoice_date or order.start_date
        if period_start and period_start == order.next_invoice_date:
            period_end = period_start + order.plan_id.billing_period
        else:
            period_end = order.next_invoice_date

        def date_filter(m):
            return (
                m.date
                and (not period_start or period_start <= m.date.date())
                and (not period_end or m.date.date() <= period_end)
            )

        return (
            outgoing_moves.filtered(date_filter),
            incoming_moves.filtered(date_filter),
        )

    def _filtered_stock_subscription_lines(self) -> Self:
        return self.filtered(
            lambda line: line.recurring_invoice and line.product_id.type == "consu"
        )

    def _get_invoice_line_parameters(self) -> tuple:
        self.check_singleton()
        if self._is_postpaid_line() and self.order_id.subscription_state == "5_renewed":
            aml = self.invoice_line_ids.filtered(
                lambda l: (
                    l.move_id.state == "posted"
                    and l.deferred_start_date
                    and l.deferred_end_date
                    and l.deferred_end_date == self.last_invoiced_date
                )
            )
            if aml:
                return aml[:1].deferred_start_date, aml[:1].deferred_end_date, 1, None
        return super()._get_invoice_line_parameters()


    def _reset_subscription_qty_to_invoice(self) -> None:
        super()._reset_subscription_qty_to_invoice()
        for line in self._filtered_stock_subscription_lines():
            line.write({"qty_to_transfer": line.product_uom_qty})

    def _reset_subscription_quantity_post_invoice(self):
        stock_subscription_line = self._filtered_stock_subscription_lines()
        stock_subscription_line.with_context(
            clean_context(self.env.context)
        )._action_launch_stock_rule()
        return super(
            SaleOrderLine, self - stock_subscription_line
        )._reset_subscription_quantity_post_invoice()

    def _get_lines_to_launch_stock_rule(self):
        stock_line_ids = []
        for line in self:
            if (
                not line.recurring_invoice
                or line.order_id.subscription_state == "7_upsell"
            ):
                stock_line_ids.append(line.id)
            elif line.qty_invoiced and line.last_invoiced_date:
                stock_line_ids.append(line.id)
            elif (
                line.order_id.subscription_state in SUBSCRIPTION_PROGRESS_STATE
                and not line.last_invoiced_date
            ):
                stock_line_ids.append(line.id)
            elif line._subscription_is_one_time_sale():
                stock_line_ids.append(line.id)
            elif line._is_postpaid_line() and line.last_invoiced_date:
                stock_line_ids.append(line.id)
        return self.env["sale.order.line"].browse(stock_line_ids)

    def _action_launch_stock_rule(self, **kwargs):
        _debug.pipeline("subscription_stock_rules", lines=self)
        """Only launch stock rule if we know they won't be empty"""
        lines = self._get_lines_to_launch_stock_rule()
        return super(SaleOrderLine, lines)._action_launch_stock_rule(**kwargs)

    @api.model
    def _get_incoming_outgoing_moves_filter(self):
        base_filter = super()._get_incoming_outgoing_moves_filter()
        if self.recurring_invoice:
            so = self.order_id
            start = so.last_invoice_date or so.start_date
            end = so.next_invoice_date

            def date_filter(m):
                return m.date and start and end and start <= m.date.date() < end

            return {
                "incoming_moves": lambda m: (
                    base_filter["incoming_moves"](m) and date_filter(m)
                ),
                "outgoing_moves": lambda m: (
                    base_filter["outgoing_moves"](m) and date_filter(m)
                ),
            }
        return base_filter

    def _get_procurement_qty(self, previous_product_qty=False):
        self.check_singleton()
        if (
            self.recurring_invoice
            and previous_product_qty
            and previous_product_qty.get(self.id, 0)
        ):
            return self.product_qty
        return super()._get_procurement_qty(previous_product_qty=previous_product_qty)

    def _prepare_procurement_vals(self):
        values = super()._prepare_procurement_vals()
        if (
            not self.recurring_invoice
            or self.order_id.subscription_state == "7_upsell"
            or self._subscription_is_one_time_sale()
        ):
            return values
        if not self.order_id.start_date or (
            self.order_id.next_invoice_date == self.order_id.start_date
            and not self.order_id.last_invoice_date
        ):
            move_date = (
                self.order_id.next_invoice_date
                + self.order_id.plan_id.billing_period
                - relativedelta(days=1)
            )
        else:
            move_date = self.order_id.next_invoice_date - relativedelta(days=1)

        current_period_start = (
            self.order_id.last_invoice_date
            or self.order_id.start_date
            or fields.Date.today()
        )
        lang_code = self.order_id.partner_id.lang
        format_start = format_date(self.env, current_period_start, lang_code=lang_code)
        format_end = format_date(self.env, move_date, lang_code=lang_code)
        values.update(
            {
                "date_planned": current_period_start,
                "date_deadline": move_date,
                "product_description_variants": f"{values.get('product_description_variants', '')}\n{format_start} to {format_end}",
            }
        )
        return values
