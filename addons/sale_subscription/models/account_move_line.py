from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.db.schema import column_exists, create_column


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def _auto_init(self):
        if not column_exists(self.env.cr, "account_move_line", "subscription_mrr"):
            create_column(
                self.env.cr, "account_move_line", "subscription_mrr", "numeric"
            )
        return super()._auto_init()

    subscription_id = fields.Many2one(
        comodel_name="sale.order",
        index=True,
    )
    subscription_mrr = fields.Monetary(
        string="Monthly Recurring Revenue",
        compute="_compute_mrr",
        store=True,
        help="The MRR is computed by dividing the signed amount (in company currency) by the "
        "amount of time between the start and end dates converted in months.\nThis allows "
        "comparison of invoice lines created by subscriptions with different temporalities.\n"
        "The computation assumes that 1 month is comprised of exactly 30 days, regardless "
        " of the actual length of the month.",
    )

    @api.depends(
        "price_subtotal",
        "deferred_start_date",
        "deferred_end_date",
        "move_id.move_type",
    )
    def _compute_mrr(self) -> None:
        for line in self:
            if not (line.deferred_end_date and line.deferred_start_date):
                line.subscription_mrr = 0
                continue
            delta = relativedelta(
                dt1=line.deferred_end_date + relativedelta(days=1),
                dt2=line.deferred_start_date,
            )
            months = delta.months + delta.days / 30.0 + delta.years * 12.0
            line.subscription_mrr = line.price_subtotal / months if months else 0
            if line.move_id.move_type == "out_refund":
                line.subscription_mrr *= -1

    def copy_data(self, default=None):
        data_list = super().copy_data(default=default)
        for line, values in zip(self, data_list, strict=False):
            if line.subscription_id:
                values["deferred_start_date"] = line.deferred_start_date
                values["deferred_end_date"] = line.deferred_end_date
        return data_list

    @api.depends("move_id.ref")
    def _compute_name(self):
        move_line_to_recompute = self
        for line in move_line_to_recompute.filtered(
            lambda l: l.move_id.inalterable_hash is False
        ):
            if line.sale_line_ids and all(
                sale_line.recurring_invoice for sale_line in line.sale_line_ids
            ):
                move_line_to_recompute -= line

        super(AccountMoveLine, move_line_to_recompute)._compute_name()

    def _sale_get_order_map(self):
        mapping_from_invoice = super()._sale_get_order_map()
        if mapping_from_invoice:
            renewed_subscriptions_ids = [
                so.id
                for so in mapping_from_invoice.values()
                if so.subscription_state == "5_renewed"
            ]
            child_orders = self.env["sale.order"].search(
                [
                    ("subscription_state", "=", "3_progress"),
                    ("origin_order_id", "in", renewed_subscriptions_ids),
                ],
                order="id ASC",
            )
            bad_aml_ids = []
            for aml_id, so in mapping_from_invoice.items():
                if so.subscription_state == "5_renewed":
                    origin_order_id = so.origin_order_id.id or so.id
                    min_child_order = next(
                        (
                            child
                            for child in child_orders
                            if child.origin_order_id.id == origin_order_id
                        ),
                        None,
                    )
                    if min_child_order:
                        mapping_from_invoice[aml_id] = min_child_order
                    else:
                        bad_aml_ids.append(aml_id)
            for aml_id in bad_aml_ids:
                del mapping_from_invoice[aml_id]
        return mapping_from_invoice

    def _get_max_invoiced_date(self):
        periods = {}

        for aml in self:
            if aml.move_id.state in ["draft", "cancel"] or not aml.deferred_end_date:
                continue
            if aml.sale_line_ids:
                target_uom = aml.sale_line_ids.product_uom_id
            elif aml.product_uom_id:
                target_uom = aml.product_uom_id
            else:
                continue
            sign = 1 if aml.move_id.move_type == "out_invoice" else -1
            periods.setdefault(aml.deferred_end_date, 0.0)
            periods[aml.deferred_end_date] += sign * abs(
                aml.product_uom_id._get_quantity_in_unit(
                    aml.quantity, target_uom, round=False
                )
            )

        invoice_dates = [d for d, qty in periods.items() if qty > 0.0]

        return invoice_dates and max(invoice_dates)
