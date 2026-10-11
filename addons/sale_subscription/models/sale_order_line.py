from collections import defaultdict

from dateutil.relativedelta import relativedelta

from odoo import Command, api, fields, models
from odoo.fields import CommandCreate, Domain
from odoo.libs.debug_log import DebugLog
from odoo.tools import float_is_zero, format_date

from .sale_order import SUBSCRIPTION_CLOSED_STATE

INTERVAL_FACTOR = {
    "day": 30.437,
    "week": 30.437 / 7.0,
    "month": 1.0,
    "year": 1.0 / 12.0,
}

_debug = DebugLog(__name__)


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    recurring_invoice = fields.Boolean(related="product_template_id.recurring_invoice")
    recurring_monthly = fields.Monetary(
        string="Monthly Recurring Revenue",
        compute="_compute_recurring_monthly",
    )
    parent_line_id = fields.Many2one(
        comodel_name="sale.order.line",
        compute="_compute_parent_line_id",
        precompute=True,
        store=True,
        index="btree_not_null",
    )
    last_invoiced_date = fields.Date(
        compute="_compute_last_invoiced_date",
        store=True,
        index=True,
    )
    pricelist_id = fields.Many2one(related="order_id.pricelist_id")
    subscription_start_date = fields.Date(related="order_id.start_date")
    subscription_end_date = fields.Date(related="order_id.end_date")
    next_invoice_date = fields.Date(related="order_id.next_invoice_date")
    product_template_variant_value_ids = fields.Many2many(
        related="product_id.product_template_variant_value_ids"
    )
    subscription_plan_id = fields.Many2one(related="order_id.plan_id")
    display_type = fields.Selection(
        selection_add=[
            ("subscription_discount", "Subscription Discount"),
        ]
    )

    @property
    def upsell_total(self):
        for line in self:
            if line.order_id.subscription_state != "7_upsell":
                return 0
            if line.parent_line_id:
                additional_qty = (
                    line.product_qty if line.state in ("draft", "sent") else 0
                )
                return line.parent_line_id.product_qty + additional_qty
            return line.product_qty
        return None

    def _filtered_unlink_forbidden(self):
        undeletable_lines = super()._filtered_unlink_forbidden()
        not_subscription_lines = self.filtered(
            lambda line: not (line.order_id.is_subscription and line.recurring_invoice)
        )
        return not_subscription_lines and undeletable_lines

    @api.depends(
        "order_id.next_invoice_date",
        "order_id.subscription_state",
        "recurring_invoice",
    )
    def _compute_invoice_state(self):
        skip_line_status_compute = self.env.context.get("skip_line_status_compute")
        if skip_line_status_compute:
            return
        super()._compute_invoice_state()
        today = fields.Date.today()
        for line in self:
            currency_id = line.order_id.currency_id or self.env.company.currency_id
            next_invoice_date = line.order_id.next_invoice_date
            last_invoiced_date = line.last_invoiced_date
            if (
                not line.order_id.is_subscription
                and line.order_id.subscription_state != "7_upsell"
            ) or not line.recurring_invoice:
                continue
            recurring_free = (
                currency_id.compare_amounts(line.order_id.recurring_monthly, 0) < 1
            )
            closed_prepaid = (
                line.invoice_state == "to do"
                and line.order_id.subscription_state in SUBSCRIPTION_CLOSED_STATE
                and not line._is_postpaid_line()
            )
            if recurring_free or closed_prepaid:
                line.invoice_state = "no"
                continue
            to_invoice_check = (
                next_invoice_date
                and line.state == "done"
                and next_invoice_date >= today
            )
            if line.order_id.end_date:
                to_invoice_check = to_invoice_check and line.order_id.end_date > today
            if to_invoice_check:
                future_line = (
                    line.order_id.start_date and line.order_id.start_date > today
                ) or (currency_id.is_zero(line.price_subtotal))
                if future_line:
                    line.invoice_state = "no"
                elif (
                    last_invoiced_date
                    and next_invoice_date
                    and next_invoice_date > today
                ):
                    line.invoice_state = "done"

    @api.depends("order_id.plan_id", "parent_line_id")
    def _compute_price_and_discount(self):
        Line = self.env["sale.order.line"]
        regular = Line
        carried = Line
        prorata_per_order = defaultdict(lambda: Line)
        for line in self:
            order = line.order_id
            if not order.subscription_state:
                regular |= line
            elif (
                line.recurring_invoice
                and order.subscription_state == "7_upsell"
                and order.subscription_id.next_invoice_date
            ):
                prorata_per_order[order._origin.id] |= line
                if line.parent_line_id:
                    carried |= line
                else:
                    regular |= line
            elif line.parent_line_id:
                carried |= line
            elif (
                line.recurring_invoice
                or order.subscription_state not in SUBSCRIPTION_CLOSED_STATE
            ):
                regular |= line
        _debug.logic(
            "subscription_price_split",
            lines=self,
            regular=regular,
            carried=carried,
            prorata_orders=len(prorata_per_order),
        )
        super(SaleOrderLine, regular)._compute_price_and_discount()
        for line in carried:
            _debug.logic(
                "price_carried_from_parent", line=line, parent=line.parent_line_id
            )
            line.price_unit = line.parent_line_id.price_unit
            line.price_unit_auto = line.parent_line_id.price_unit
        for lines in prorata_per_order.values():
            lines._apply_upsell_prorata_discount()

    def _apply_upsell_prorata_discount(self) -> None:
        force_recompute = self.env.context.get("force_price_recomputation")
        origin_discount_auto = {
            origin.id: origin.discount_auto for origin in self._origin
        }
        prorata_per_order = defaultdict(lambda: self.env["sale.order.line"])
        for line in self:
            order = line.order_id
            if (
                line.recurring_invoice
                and order.subscription_state == "7_upsell"
                and order.subscription_id.next_invoice_date
            ):
                prorata_per_order[order._origin.id] |= line
        for so_id, lines in prorata_per_order.items():
            order_id = self.env["sale.order"].browse(so_id)
            ratio = order_id._get_ratio_value()
            line_to_discount, _dummy = lines._get_renew_discount_info(
                upsell_ratio=ratio
            )
            for line in line_to_discount:
                if line.parent_line_id and line.parent_line_id.discount:
                    auto_discount = (
                        1 - ratio * (1 - line.parent_line_id.discount / 100)
                    ) * 100
                else:
                    auto_discount = (1 - ratio) * 100
                old_auto_discount = line.discount_auto or origin_discount_auto.get(
                    line._origin.id, 0.0
                )
                _debug.logic(
                    "upsell_prorata_discount",
                    line=line,
                    ratio=ratio,
                    auto=auto_discount,
                    old_auto=old_auto_discount,
                )
                if line._is_discount_update_required(
                    auto_discount, old_auto_discount, force_recompute
                ):
                    line.discount = auto_discount
                line.discount_auto = auto_discount

    @api.depends("order_id.plan_id")
    def _compute_pricelist_item_id(self) -> None:
        super()._compute_pricelist_item_id()

    @api.depends(
        "recurring_invoice",
        "invoice_line_ids.deferred_start_date",
        "invoice_line_ids.deferred_end_date",
        "order_id.next_invoice_date",
        "order_id.last_invoice_date",
        "order_id.end_date",
        "order_id.subscription_state",
        "recurring_monthly",
    )
    def _compute_invoice_amounts(self):
        super()._compute_invoice_amounts()
        subscription_qty_invoiced = self._get_subscription_qty_invoiced()
        subscription_qty_draft = self._get_subscription_qty_invoiced(draft=True)
        for line in self:
            if line.display_type or not (
                line.recurring_invoice and line.order_id.plan_id
            ):
                continue
            line.qty_invoiced = subscription_qty_invoiced.get(line.id, 0.0)
            line.qty_invoiced_draft = subscription_qty_draft.get(line.id, 0.0)
            if line.state in ("draft", "cancel") or line.product_type == "combo":
                continue
            qty_to_consider = (
                line.qty_transferred
                if line.product_id.invoice_policy == "transferred"
                else line.product_qty
            )
            line.qty_to_invoice = (
                qty_to_consider - line.qty_invoiced - line.qty_invoiced_draft
            )

        for line in self:
            order = line.order_id
            today = fields.Date.context_today(order)

            is_invoice_due = not order.last_invoice_date or (
                order.next_invoice_date <= today and order.last_invoice_date <= today
            )
            if not is_invoice_due:
                line.amount_taxexc_to_invoice = 0.0
                line.amount_taxinc_to_invoice = 0.0
                continue

            is_order_active = order.subscription_state in (
                "3_progress",
                "4_paused",
            ) and (not order.end_date or order.next_invoice_date < order.end_date)
            if (
                line.recurring_invoice
                and is_order_active
                and not line.currency_id.is_zero(line.price_subtotal)
            ):
                recurring_monthly_tax_incl = (
                    line.recurring_monthly / line.price_subtotal
                ) * line.price_total
                line.amount_taxinc_to_invoice = recurring_monthly_tax_incl

    @api.depends(
        "invoice_line_ids.deferred_end_date",
        "invoice_line_ids.move_id.state",
        "invoice_line_ids.subscription_id",
    )
    def _compute_last_invoiced_date(self) -> None:
        result_by_subscription_id = self.env["account.move.line"]._read_group(
            [
                ("subscription_id", "in", self.order_id.ids),
                ("move_id.state", "=", "posted"),
                ("move_id.move_type", "in", ["out_invoice", "out_refund"]),
                ("deferred_end_date", "!=", False),
            ],
            aggregates=["id:recordset"],
            groupby=["subscription_id"],
        )
        result_by_order = {}
        for order, move_lines in result_by_subscription_id:
            result_by_order[order.id] = move_lines._get_max_invoiced_date()
        result_by_sale_line_ids = self.env["account.move.line"]._read_group(
            [
                ("sale_line_ids", "in", self.ids),
                ("move_id.state", "=", "posted"),
                ("move_id.move_type", "in", ["out_invoice", "out_refund"]),
                ("deferred_end_date", "!=", False),
            ],
            aggregates=["id:recordset"],
            groupby=["sale_line_ids"],
        )
        self.last_invoiced_date = False
        for line, move_lines in result_by_sale_line_ids:
            line.last_invoiced_date = (
                move_lines._get_max_invoiced_date()
                or result_by_order.get(line.order_id.id)
            )

    def _get_invoice_lines(self):
        self.check_singleton()
        if self._is_not_recurring_invoice():
            return super()._get_invoice_lines()
        else:
            last_invoice_date = (
                self.order_id.last_invoice_date or self.order_id.start_date
            )
            return self.invoice_line_ids.filtered(
                lambda line: (
                    line.date and last_invoice_date and line.date > last_invoice_date
                )
            )

    def _get_deferred_date(
        self, last_invoiced_date=None, next_invoice_date=None
    ) -> tuple:
        self.check_singleton()
        if last_invoiced_date and next_invoice_date:
            return last_invoiced_date, next_invoice_date
        deferred_start_date = (
            self.last_invoiced_date and self.last_invoiced_date + relativedelta(days=1)
        ) or self.order_id.start_date
        if self._is_postpaid_line():
            deferred_end_date = (
                deferred_start_date
                + self.order_id.plan_id.billing_period
                - relativedelta(days=1)
            )
        else:
            if not self.order_id.next_invoice_date:
                return False, False
            next_invoice_date = self.order_id.next_invoice_date
            if self.last_invoiced_date:
                deferred_start_date = self.last_invoiced_date
                deferred_end_date = (
                    self.last_invoiced_date
                    + self.order_id.plan_id.billing_period
                    - relativedelta(days=1)
                )
            else:
                deferred_start_date = (
                    next_invoice_date - self.order_id.plan_id.billing_period
                )
                deferred_end_date = next_invoice_date - relativedelta(days=1)
        return deferred_start_date, deferred_end_date

    def _get_subscription_qty_invoiced(
        self, last_invoiced_date=None, next_invoice_date=None, draft=False
    ):
        move_state = "draft" if draft else "posted"
        result = {}
        amount_sign = {"out_invoice": 1, "out_refund": -1}
        stored_lines = self.filtered("id")
        upsells_by_parent = (
            self.env["sale.order.line"]
            .sudo()
            .search(
                [
                    ("parent_line_id", "in", stored_lines.ids),
                    ("state", "=", "done"),
                    ("order_id.subscription_state", "=", "7_upsell"),
                ]
            )
            .grouped("parent_line_id")
            if stored_lines
            else {}
        )
        for line in self:
            if not line.recurring_invoice or line.order_id.state != "done":
                continue
            if line._subscription_is_one_time_sale():
                continue
            upsell_lines = upsells_by_parent.get(line, ())
            if not line.invoice_line_ids and not upsell_lines:
                continue
            period_start, period_end = line._get_deferred_date(
                last_invoiced_date=last_invoiced_date,
                next_invoice_date=next_invoice_date,
            )
            if not period_start or not period_end:
                continue
            qty_invoiced = (
                0.0
                if draft
                else sum(
                    upsell.product_uom_id._get_quantity_in_unit(
                        upsell.product_qty, line.product_uom_id
                    )
                    for upsell in upsell_lines
                    if upsell.order_id.start_date
                    and period_start <= upsell.order_id.start_date <= period_end
                )
            )
            period = period_end if line._is_postpaid_line() else period_start
            related_invoice_lines = line.invoice_line_ids.filtered_domain(
                [
                    ("move_id.state", "=", move_state),
                    ("deferred_start_date", "!=", False),
                    ("deferred_end_date", "=", period),
                ]
            )
            for invoice_line in related_invoice_lines:
                line_sign = amount_sign.get(invoice_line.move_id.move_type, 1)
                qty_invoiced += (
                    line_sign
                    * invoice_line.product_uom_id._get_quantity_in_unit(
                        invoice_line.quantity, line.product_uom_id
                    )
                )
            result[line.id] = qty_invoiced
        return result

    def _prepare_qty_invoiced(self):
        subscription_invoiced_qties = defaultdict(float)
        other_lines = self.env["sale.order.line"]
        subscription_qty_invoiced = self._get_subscription_qty_invoiced()
        for line in self:
            if line._is_not_recurring_invoice():
                other_lines |= line
                continue
            subscription_invoiced_qties[line] = subscription_qty_invoiced.get(
                line.id, 0.0
            )
        invoiced_qties = super(SaleOrderLine, other_lines)._prepare_qty_invoiced()
        invoiced_qties.update(subscription_invoiced_qties)
        return invoiced_qties

    @api.depends("recurring_invoice", "price_subtotal")
    def _compute_recurring_monthly(self) -> None:
        for line in self:
            if not line.recurring_invoice or not line.order_id.plan_id.billing_period:
                line.recurring_monthly = 0
            else:
                line.recurring_monthly = (
                    line.price_subtotal
                    * INTERVAL_FACTOR[line.order_id.plan_id.repeat_unit]
                    / line.order_id.plan_id.repeat_interval
                )

    @api.depends(
        "order_id.subscription_id",
        "product_id",
        "product_uom_id",
        "price_unit",
        "order_id",
        "order_id.plan_id",
        "order_id.subscription_id.line_ids",
    )
    def _compute_parent_line_id(self) -> None:
        for order, lines in self.grouped("order_id").items():
            parent_lines_by_key = defaultdict(list)
            for parent_line in order.subscription_id.line_ids:
                parent_lines_by_key[
                    parent_line.order_id, *parent_line._get_parent_line_matching_key()
                ].append(parent_line)
            for line in lines:
                if (
                    not line.order_id.subscription_id
                    or not line.product_id.recurring_invoice
                ):
                    line.parent_line_id = False
                    continue
                matching_parent_lines = parent_lines_by_key.get(
                    (
                        line.order_id.subscription_id,
                        *line._get_parent_line_matching_key(),
                    )
                )
                if matching_parent_lines:
                    line.parent_line_id = matching_parent_lines.pop()._origin
                else:
                    line.parent_line_id = False

    def _get_parent_line_matching_key(self) -> tuple:
        self.check_singleton()
        currency = self.order_id.currency_id
        return (
            self.product_id,
            self.product_uom_id,
            currency,
            self.order_id.plan_id,
            currency.round(self.price_unit) if currency else round(self.price_unit, 2),
        )

    def _get_invoice_line_parameters(self) -> tuple:
        self.check_singleton()
        today = fields.Date.today()
        start_date = self.order_id.start_date or today
        first_contract_date = self.order_id.first_contract_date or start_date
        is_upsell = self.order_id.subscription_state == "7_upsell"
        force_postpaid_next_invoice = self.env.context.get(
            "force_postpaid_next_invoice"
        )
        if is_upsell:
            new_period_start = max(start_date, first_contract_date)
            new_period_stop = self.order_id.next_invoice_date
        elif self._is_postpaid_line() and not force_postpaid_next_invoice:
            new_period_start = (
                (
                    self.last_invoiced_date
                    and self.last_invoiced_date + relativedelta(days=1)
                )
                or self.order_id.last_invoice_date
                or start_date
            )
            theoretical_stop = (
                new_period_start
                and new_period_start + self.order_id.plan_id.billing_period
            )
            new_period_stop = min(
                date for date in [theoretical_stop, self.order_id.end_date] if date
            )
        else:
            new_period_start = self.order_id.next_invoice_date or max(
                start_date, first_contract_date
            )
            new_period_stop = new_period_start + self.order_id.plan_id.billing_period

        if (
            not self.order_id.plan_id.billing_first_day
            or self.order_id.plan_id.repeat_unit == "week"
        ):
            return new_period_start, new_period_stop - relativedelta(days=1), 1, None
        elif self.order_id.plan_id.repeat_unit == "month":
            reference_date = (
                new_period_stop
                if new_period_stop >= today
                else new_period_stop + relativedelta(months=1)
            )
            next_date_1st = reference_date + relativedelta(day=1)
        elif self.order_id.plan_id.repeat_unit == "year":
            reference_date = (
                new_period_stop
                if new_period_stop >= today
                else new_period_stop + relativedelta(years=1)
            )
            next_date_1st = reference_date + relativedelta(day=1, month=1)

        number_of_days = (next_date_1st - new_period_start).days
        ratio = number_of_days / (new_period_stop - new_period_start).days
        if self._is_delivery() or not self.product_id.allow_prorated_price:
            ratio = 1
        return (
            new_period_start,
            next_date_1st - relativedelta(days=1),
            ratio,
            number_of_days,
        )

    def _prepare_aml_vals(self, **optional_values):
        self.check_singleton()
        res = super()._prepare_aml_vals(**optional_values)
        if self.display_type or self.product_id.type == "combo":
            if res.get("display_type") == "subscription_discount":
                res.update({"display_type": "line_note"})
            return res
        elif self.order_id.plan_id and (
            self.recurring_invoice or self.order_id.subscription_state == "7_upsell"
        ):
            lang_code = self.order_id.partner_id.lang
            parent_order_id = (
                self.order_id.subscription_id.id
                if self.order_id.subscription_state == "7_upsell"
                else self.order_id.id
            )
            duration = self.order_id.plan_id.billing_period_display

            new_period_start, new_period_stop, ratio, number_of_days = (
                self._get_invoice_line_parameters()
            )
            if ratio != 1:
                duration = self.env._("%s days", number_of_days)
                res["price_unit"] *= ratio

            if (
                self.order_id.subscription_state == "7_upsell"
                and self.order_id.plan_id.billing_first_day
            ):
                duration = self.env._("%s days", number_of_days)

            description = res.get("name") or self.name
            if self.recurring_invoice and not self._is_delivery():
                format_start = format_date(
                    self.env, new_period_start, lang_code=lang_code
                )
                format_next = format_date(
                    self.env, new_period_stop, lang_code=lang_code
                )
                start_to_next = self.env._(
                    "%(start)s to %(next)s", start=format_start, next=format_next
                )
                description += f"\n{duration} {start_to_next}"

            if self.order_id.subscription_state != "7_upsell":
                line_to_invoice = self._is_subscription_line_to_invoice()
                if line_to_invoice:
                    if self._is_postpaid_line():
                        qty_to_invoice = self.qty_transferred
                    else:
                        qty_to_invoice = self.product_qty
                else:
                    qty_to_invoice = 0
            else:
                qty_to_invoice = self.qty_to_invoice if not self.is_downpayment else 1.0
            res.update(
                {
                    "name": description,
                    "quantity": qty_to_invoice,
                    "deferred_start_date": new_period_start,
                    "deferred_end_date": new_period_stop,
                    "subscription_id": parent_order_id,
                }
            )
        elif self.order_id.is_subscription and not res.get("subscription_id"):
            res.update(
                {
                    "subscription_id": self.order_id.id,
                }
            )
        return res

    def _reset_subscription_qty_to_invoice(self) -> None:
        today = fields.Date.today()
        for line in self:
            if (
                not line.recurring_invoice
                or line._is_postpaid_line()
                or (line.order_id.start_date and line.order_id.start_date > today)
            ):
                _debug.logic("qty_to_invoice_kept", line=line, reason="not_due")
                continue
            line.qty_to_invoice = line.product_qty

    def _reset_subscription_quantity_post_invoice(self):
        return

    def _get_recurring_invoiceable_condition(self, automatic_invoice, date_from):
        self.check_singleton()
        if automatic_invoice:
            return (
                self.order_id.next_invoice_date
                and self.order_id.next_invoice_date <= date_from
                and self.order_id.start_date
                and self.order_id.start_date <= date_from
            )
        elif self._is_postpaid_line():
            return bool(self.order_id.start_date != self.order_id.next_invoice_date)
        else:
            return not self.order_id.end_date or (
                self.order_id.next_invoice_date
                and self.order_id.next_invoice_date < self.order_id.end_date
            )

    def _is_invoiceable(self, final=False) -> bool:
        if self.state != "done" or self.display_type == "subscription_discount":
            return False
        if super()._is_invoiceable(final) and (
            not self.recurring_invoice
            or self.order_id.subscription_state == "7_upsell"
            or self._subscription_is_one_time_sale()
        ):
            return True
        return bool(self._is_subscription_line_to_invoice())

    def _is_subscription_line_to_invoice(self) -> bool:
        self.check_singleton()
        date_from = self.env.context.get("invoiceable_date_from", fields.Date.today())
        automatic_invoice = self.env.context.get("recurring_automatic")
        line_to_invoice = False
        line_condition = self._get_recurring_invoiceable_condition(
            automatic_invoice, date_from
        )
        if (
            self.order_id.subscription_state == "7_upsell"
            or self.display_type
            or not self.recurring_invoice
        ):
            line_to_invoice = False
        elif line_condition:
            if (
                self.product_id.invoice_policy == "ordered"
                and self.order_id.subscription_state != "5_renewed"
                and not float_is_zero(
                    self.product_qty,
                    precision_rounding=self.product_id.uom_id.rounding,
                )
            ) or (
                self._is_postpaid_line()
                and not float_is_zero(
                    self.qty_transferred,
                    precision_rounding=self.product_id.uom_id.rounding,
                )
            ):
                line_to_invoice = True
        _debug.logic(
            "subscription_line_to_invoice",
            line=self,
            invoice=line_to_invoice,
            condition=line_condition,
            automatic=bool(automatic_invoice),
        )
        return bool(line_to_invoice)

    def _get_renew_discount_info(self, upsell_ratio=0, start_date=None) -> tuple:
        order = self.order_id
        if len(order) != 1:
            return self.env["sale.order.line"], ""
        today = fields.Date.today()
        start_date = start_date or order.start_date or today
        next_invoice_date = (
            order.next_invoice_date or order.subscription_id.next_invoice_date
        )
        end_date = next_invoice_date - relativedelta(days=1)
        if start_date >= end_date:
            line_name = self.env._(
                "(*) These recurring products are entirely discounted as the next period has not been invoiced yet."
            )
        else:
            format_start = format_date(self.env, start_date)
            format_end = format_date(self.env, end_date)
            if upsell_ratio <= 1:
                line_name = self.env._(
                    "(*) These recurring products are discounted according to the prorated period from %(start)s to %(end)s",
                    start=format_start,
                    end=format_end,
                )
            else:
                line_name = self.env._(
                    "(*) These recurring products are surcharged according to the prorated period from %(start)s to %(end)s",
                    start=format_start,
                    end=format_end,
                )
        return self.filtered_domain(self._get_domain_renew_discount()), line_name

    def _create_update_subscription_discount_values(
        self, updell_ratio=0, discount_comment=""
    ) -> None:
        line_note_found = False
        line_note_needed = self and updell_ratio != 1
        for line in self.order_id.line_ids:
            if line in self and updell_ratio != 1 and "(*)" not in line.name:
                line.name += "(*)"
            if line.display_type == "subscription_discount":
                line.name = discount_comment
                line_note_found = True
        if not line_note_found and line_note_needed:
            self.order_id.line_ids = [
                Command.create(
                    {
                        "display_type": "subscription_discount",
                        "sequence": 999,
                        "name": discount_comment,
                        "product_qty": 0,
                    }
                )
            ]

    def _get_domain_renew_discount(self):
        domain = [
            ("recurring_invoice", "=", True),
            ("product_id.allow_prorated_price", "=", True),
        ]
        if "is_delivery" in self:
            domain = Domain.AND([domain, [(("is_delivery", "=", False))]])
        return domain

    def _prepare_renew_upsell_line_commands(
        self, subscription_state
    ) -> list[CommandCreate]:
        order_lines = []
        description_needed, description_name = [], ""
        if subscription_state == "7_upsell":
            if len(self.order_id) > 1:
                ratio = 0
            else:
                ratio = self.order_id._get_ratio_value(new_upsell=True)
            description_needed, description_name = self._get_renew_discount_info(
                upsell_ratio=ratio, start_date=fields.Date.context_today(self)
            )
        for line in self:
            is_note_or_section = line.display_type in [
                "line_section",
                "line_subsection",
                "line_note",
            ]
            if not line.recurring_invoice and not is_note_or_section:
                continue
            if subscription_state == "7_upsell" and line._is_postpaid_line():
                continue
            partner_lang = line.order_id.partner_id.lang
            line = line.with_context(lang=partner_lang) if partner_lang else line
            product = line.product_id
            line_values = {
                "parent_line_id": line.id,
                "name": line.name + "(*)" if line in description_needed else line.name,
                "product_id": product.id,
                "product_uom_id": line.product_uom_id.id,
                "product_qty": 0
                if subscription_state == "7_upsell"
                else line.product_qty,
                "price_unit": line.price_unit,
                "display_type": line.display_type,
                "is_optional": line.is_optional,
            }
            if line._is_delivery():
                line_values.update({"is_delivery": True})
            order_lines.append((0, 0, line_values))

        order_lines = self._filter_non_empty_sections(order_lines)

        if description_needed and description_name:
            order_lines.append(
                (
                    0,
                    0,
                    {
                        "display_type": "subscription_discount",
                        "sequence": 999,
                        "name": description_name,
                        "product_qty": 0,
                    },
                )
            )

        return order_lines

    def _filter_non_empty_sections(
        self, order_lines: list[tuple[int, int, dict]]
    ) -> list[tuple[int, int, dict]]:
        filtered_order_lines = []
        for index, line in enumerate(order_lines):
            is_section = (
                line[2].get("display_type") in ("line_section", "line_subsection")
                if len(line) == 3
                else False
            )
            if not is_section:
                filtered_order_lines.append(line)
                continue
            next_line = order_lines[index + 1] if index + 1 < len(order_lines) else None
            should_keep = (
                next_line is not None
                and len(next_line) == 3
                and next_line[2].get("display_type") != "line_section"
            )
            if should_keep:
                filtered_order_lines.append(line)
        return filtered_order_lines

    def _subscription_update_line_data(self, subscription) -> tuple:
        update_values = []
        create_values = []
        dict_changes = {}
        for line in self:
            sub_line = line.parent_line_id
            if sub_line:
                if len(sub_line) > 1:
                    sub_line[0].copy(
                        {"name": line.display_name, "product_qty": line.product_qty}
                    )
                elif line.product_qty != 0:
                    dict_changes.setdefault(sub_line.id, sub_line.product_qty)
                    dict_changes[sub_line.id] += line.product_qty
            elif line.recurring_invoice:
                create_values.append(
                    Command.create(
                        {
                            "product_id": line.product_id.id,
                            "name": line.name,
                            "product_qty": line.product_qty,
                            "product_uom_id": line.product_uom_id.id,
                            "price_unit": line.price_unit,
                            "discount": 0,
                            "order_id": subscription.id,
                        }
                    )
                )
        update_values += [
            (1, sub_id, {"product_qty": dict_changes[sub_id]})
            for sub_id in dict_changes
        ]
        return create_values, update_values

    def _get_pricelist_price(self):
        if self.recurring_invoice:
            return super()._get_pricelist_price() or self.price_unit
        return super()._get_pricelist_price()

    def _get_pricelist_kwargs(self):
        res = super()._get_pricelist_kwargs()
        if self.recurring_invoice:
            res["plan_id"] = self.order_id.plan_id.id
        return res

    def _is_postpaid_line(self) -> bool:
        self.check_singleton()
        return self.product_id.invoice_policy == "transferred"

    def _is_all_postpaid(self) -> bool:
        results = []
        for line in self:
            if not line.recurring_invoice:
                continue
            if line._is_postpaid_line():
                results.append(True)
            else:
                results.append(False)
        return all(results)

    def _is_not_recurring_invoice(self) -> bool:
        self.check_singleton()
        return not (self.recurring_invoice and self.order_id.plan_id)

    def _subscription_is_one_time_sale(self):
        self.check_singleton()
        return (
            self.product_id.allow_one_time_sale
            and self.recurring_invoice
            and not self.order_id.plan_id
        )
