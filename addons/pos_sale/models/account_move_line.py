from odoo import models
from odoo.tools import float_compare


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def _get_downpayment_lines(self):
        downpayment_lines = self.env["account.move.line"]
        if not self.env["pos.order.line"].has_access("read"):
            return super()._get_downpayment_lines()

        for record in self:
            if related_sol := record.sale_line_ids:
                pos_downpayment_moves = related_sol.filtered(
                    "is_downpayment"
                ).pos_order_line_ids.order_id.account_move
                downpayment_lines |= record._get_matching_downpayment_lines(
                    pos_downpayment_moves.invoice_line_ids
                )

            elif related_posl := record.move_id.pos_order_ids.lines:
                sale_orders = related_posl.sale_order_origin_id
                candidate_moves = (
                    sale_orders.pos_order_line_ids.order_id.account_move.filtered(
                        lambda r: r._is_downpayment()
                    )
                )
                applicable_lines = record._get_matching_downpayment_lines(
                    candidate_moves.invoice_line_ids
                )

                move_lines = record.move_id.invoice_line_ids
                if len(applicable_lines) > 1 and len(move_lines) == len(
                    applicable_lines
                ):
                    lines_dict = dict(
                        zip(
                            move_lines.sorted("id"),
                            applicable_lines.sorted("id"),
                            strict=False,
                        )
                    )
                    downpayment_lines |= (
                        lines_dict.get(record) or self.env["account.move.line"]
                    )
                else:
                    downpayment_lines |= applicable_lines

        return downpayment_lines | super()._get_downpayment_lines()

    def _get_matching_downpayment_lines(self, lines):
        self.check_singleton()
        rounding = self.currency_id.rounding
        return lines.filtered(
            lambda line: (
                float_compare(
                    line.price_subtotal,
                    -self.price_subtotal,
                    precision_rounding=rounding,
                )
                == 0
                and line.tax_ids == self.tax_ids
            )
        )
