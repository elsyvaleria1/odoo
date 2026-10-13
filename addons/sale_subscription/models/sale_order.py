import logging
import traceback
from collections import defaultdict
from datetime import timedelta
from itertools import batched
from typing import Self

from dateutil.relativedelta import relativedelta
from markupsafe import Markup, escape
from psycopg.errors import (
    DeadlockDetected,
    SerializationFailure,
    TransactionRollback,
)

from odoo import api, fields, models, modules
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command, Domain
from odoo.libs.debug_log import DebugLog
from odoo.modules.module import can_commit
from odoo.tools import format_amount, plaintext2html, str2bool
from odoo.tools.misc import format_date

from odoo.addons.trade.models.mixin_order import MixinOrder

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)

TransactionRollbackError = (TransactionRollback, SerializationFailure, DeadlockDetected)

SUBSCRIPTION_DRAFT_STATE = ["1_draft", "2_renewal"]
SUBSCRIPTION_PROGRESS_STATE = ["3_progress", "4_paused"]
SUBSCRIPTION_CLOSED_STATE = ["6_churn", "5_renewed"]

SUBSCRIPTION_STATES = [
    ("1_draft", "Quotation"),
    ("2_renewal", "Renewal Quotation"),
    (
        "3_progress",
        "In Progress",
    ),
    ("4_paused", "Paused"),
    ("5_renewed", "Renewed"),
    ("6_churn", "Churned"),
    ("7_upsell", "Upsell"),
]


class SaleOrder(models.Model):
    _name = "sale.order"
    _inherit = ["mixin.rating", "sale.order"]
    _LOCKED_WRITABLE_FIELDS = MixinOrder._LOCKED_WRITABLE_FIELDS | {
        "end_date",
        "close_reason_id",
        "subscription_state",
        "payment_token_id",
        "payment_exception",
        "internal_note",
    }

    def _get_default_starred_user_ids(self) -> list:
        return [Command.link(self.env.uid)]

    is_subscription = fields.Boolean(
        string="Recurring",
        compute="_compute_is_subscription",
        store=True,
        index=True,
    )
    plan_id = fields.Many2one(
        comodel_name="sale.subscription.plan",
        string="Recurring Plan",
        compute="_compute_plan_id",
        store=True,
        index="btree_not_null",
        readonly=False,
        ondelete="restrict",
        tracking=True,
    )
    subscription_state = fields.Selection(
        selection=SUBSCRIPTION_STATES,
        string="Subscription Status",
        compute="_compute_subscription_state",
        store=True,
        index="btree_not_null",
        readonly=False,
        group_expand="_group_expand_states",
        tracking=True,
    )

    subscription_id = fields.Many2one(
        comodel_name="sale.order",
        string="Parent Contract",
        index="btree_not_null",
        copy=False,
        ondelete="restrict",
    )
    origin_order_id = fields.Many2one(
        comodel_name="sale.order",
        string="First contract",
        compute="_compute_origin_order_id",
        store=True,
        index="btree_not_null",
        copy=False,
        ondelete="restrict",
    )
    subscription_child_ids = fields.One2many(
        comodel_name="sale.order",
        inverse_name="subscription_id",
    )
    subscription_invoice_line_ids = fields.One2many(
        comodel_name="account.move.line",
        inverse_name="subscription_id",
    )

    start_date = fields.Date(
        compute="_compute_start_date",
        store=True,
        readonly=False,
        tracking=True,
        help="The start date indicate when the subscription periods begin.",
    )
    last_invoice_date = fields.Date(
        string="Last invoice date",
        compute="_compute_last_invoice_date",
    )
    next_invoice_date = fields.Date(
        string="Next Invoice",
        compute="_compute_next_invoice_date",
        store=True,
        copy=False,
        readonly=False,
        tracking=True,
        help="The next invoice will be created on this date then the period will be extended.",
    )
    end_date = fields.Date(
        tracking=True,
        help="If set in advance, the subscription will be set to renew 1 month before the date and will be closed on the date set in this field.",
    )
    first_contract_date = fields.Date(
        compute="_compute_first_contract_date",
        store=True,
        help="The first contract date is the start date of the first contract of the sequence. It is common across a subscription and its renewals.",
    )
    close_reason_id = fields.Many2one(
        comodel_name="sale.order.close.reason",
        copy=False,
        tracking=True,
    )

    payment_token_id = fields.Many2one(
        comodel_name="payment.token",
        copy=False,
        domain="[('partner_id', 'child_of', commercial_partner_id), ('company_id', '=', company_id)]",
        check_company=True,
        help="If not set, the automatic payment will fail.",
    )
    is_batch = fields.Boolean(
        default=False,
        copy=False,
    )
    is_invoice_cron = fields.Boolean(
        string="Is a Subscription invoiced in cron",
        default=False,
        copy=False,
    )
    payment_exception = fields.Boolean(
        string="Contract in exception",
        copy=False,
        help="Automatic payment with token failed. The payment provider configuration and token should be checked",
    )
    pending_transaction = fields.Boolean(
        copy=False,
        help="The last transaction of the order is currently pending",
    )
    payment_term_id = fields.Many2one(tracking=True)
    currency_id = fields.Many2one(tracking=True)
    last_reminder_date = fields.Date(help="Last time when we sent a payment reminder")
    user_pause_start = fields.Date()

    kpi_1month_mrr_delta = fields.Float(string="KPI 1 Month MRR Delta")
    kpi_1month_mrr_percentage = fields.Float(string="KPI 1 Month MRR Percentage")
    kpi_3months_mrr_delta = fields.Float(string="KPI 3 months MRR Delta")
    kpi_3months_mrr_percentage = fields.Float(string="KPI 3 Months MRR Percentage")

    team_user_id = fields.Many2one(
        comodel_name="res.users",
        related="team_id.user_id",
        string="Team Leader",
        readonly=False,
    )
    commercial_partner_id = fields.Many2one(
        comodel_name="res.partner",
        related="partner_id.commercial_partner_id",
    )

    recurring_total = fields.Monetary(
        string="Recurring Amount",
        compute="_compute_recurring_total",
        store=True,
    )
    recurring_monthly = fields.Monetary(
        string="MRR",
        compute="_compute_recurring_monthly",
        store=True,
        tracking=True,
    )
    non_recurring_total = fields.Monetary(
        string="Total Non Recurring Revenue",
        compute="_compute_non_recurring_total",
    )
    order_log_ids = fields.One2many(
        comodel_name="sale.order.log",
        inverse_name="order_id",
        string="Subscription Logs",
        copy=False,
        readonly=True,
    )
    percentage_satisfaction = fields.Integer(
        string="% Happy",
        compute="_compute_percentage_satisfaction",
        compute_sudo=True,
        default=-1,
        store=True,
        help="Calculate the ratio between the number of the best ('great') ratings and the total number of ratings",
    )

    note_order = fields.Many2one(
        comodel_name="sale.order",
        compute="_compute_note_order",
        search="_search_note_order",
    )
    internal_note = fields.Html()
    internal_note_display = fields.Html(
        compute="_compute_internal_note_display",
        inverse="_inverse_internal_note_display",
    )
    is_closing = fields.Boolean(
        string="To Be Closed",
        compute="_compute_is_closing",
        store=True,
    )
    warn_system_closing = fields.Boolean(compute="_compute_warn_system_closing")

    recurring_details = fields.Html(compute="_compute_recurring_details")
    is_renewing = fields.Boolean(compute="_compute_is_renewing")
    is_upselling = fields.Boolean(compute="_compute_is_upselling")
    display_late = fields.Boolean(compute="_compute_display_late")
    history_count = fields.Integer(compute="_compute_history_count")
    upsell_count = fields.Integer(compute="_compute_upsell_count")
    renewal_count = fields.Integer(compute="_compute_renewal_count")
    has_recurring_line = fields.Boolean(compute="_compute_has_recurring_line")

    starred_user_ids = fields.Many2many(
        comodel_name="res.users",
        relation="sale_order_starred_user_rel",
        column1="order_id",
        column2="user_id",
        string="Members",
        default=lambda s: s._get_default_starred_user_ids(),
    )
    starred = fields.Boolean(
        string="Show Subscription on dashboard",
        compute="_compute_starred",
        inverse="_inverse_starred",
        help="Whether this subscription should be displayed on the dashboard or not",
    )

    user_closable = fields.Boolean(related="plan_id.user_closable")
    user_quantity = fields.Boolean(related="plan_id.user_quantity")
    user_extend = fields.Boolean(related="plan_id.user_extend")

    _sale_subscription_state_coherence = models.Constraint(
        "CHECK(NOT (is_subscription=TRUE AND state = 'done' AND subscription_state='1_draft'))",
        "You cannot set to draft a confirmed subscription. Please create a new quotation",
    )
    _sale_subscription_state_coherence_2 = models.Constraint(
        "CHECK(NOT (is_subscription=TRUE AND state in ('draft', 'sent') AND subscription_state in ('3_progress', '4_paused')) )",
        "You cannot have a draft SO be a confirmed subscription.",
    )
    _check_start_date_lower_next_invoice_date = models.Constraint(
        "CHECK((next_invoice_date IS NULL OR start_date IS NULL) OR (next_invoice_date >= start_date))",
        "The next invoice date of a sale order should be after its start date.",
    )

    @api.constrains("subscription_state", "subscription_id", "pricelist_id")
    def _check_subscription_upsell_multi_currency(self) -> None:
        for so in self:
            if (
                so.subscription_state == "7_upsell"
                and so.subscription_id.pricelist_id.currency_id
                != so.pricelist_id.currency_id
            ):
                raise ValidationError(
                    self.env._(
                        "You cannot upsell a subscription using a different currency."
                    )
                )

    @api.constrains("plan_id", "state", "line_ids")
    def _check_subscription_plan(self) -> None:
        for so in self:
            if so.state in ["draft", "cancel"] or so.subscription_state == "7_upsell":
                continue
            if so.subscription_id and not so.subscription_state:
                continue
            if not so.plan_id and (
                so.has_recurring_line and not so._subscription_is_one_time_sale()
            ):
                raise UserError(
                    self.env._(
                        "Please add a recurring plan on the subscription or remove the recurring product."
                    )
                )
            if so.plan_id and not so.has_recurring_line:
                raise UserError(
                    self.env._(
                        "Please add a recurring product in the subscription or remove the recurring plan."
                    )
                )

    @api.constrains("subscription_state", "state")
    def _check_canceled_subscription(self) -> None:
        incompatible_states = SUBSCRIPTION_PROGRESS_STATE + ["5_renewed"]
        for so in self:
            if so.state == "cancel" and so.subscription_state in incompatible_states:
                raise ValidationError(
                    self.env._(
                        "A cancelled SO cannot be in progress. You should close %s before cancelling it.",
                        so.name,
                    )
                )

    @api.depends("plan_id")
    def _compute_is_subscription(self) -> None:
        for order in self:
            if not order.plan_id or order.subscription_state == "7_upsell":
                order.is_subscription = False
                continue
            order.is_subscription = True
        self.env.add_to_compute(
            self.env["sale.order"]._fields["subscription_state"], self
        )

    @api.depends("is_subscription")
    def _compute_subscription_state(self) -> None:
        for order in self:
            if order.state not in ["draft", "sent"] or order.subscription_state in [
                "2_renewal",
                "7_upsell",
            ]:
                continue
            if order.is_subscription:
                order.subscription_state = (
                    "2_renewal" if order.subscription_id else "1_draft"
                )
            else:
                order.subscription_state = False

    def _compute_template_id(self):
        if not self.env.context.get("default_is_subscription", False):
            return super()._compute_template_id()
        for order in self:
            if (
                not order._origin.id
                and order.company_id.sale_config_id.sale_order_template_id.is_subscription
            ):
                order.template_id = (
                    order.company_id.sale_config_id.sale_order_template_id
                )
        return None

    def _compute_type_name(self) -> None:
        other_orders = self.env["sale.order"]
        for order in self:
            if order.is_subscription and order.state == "done":
                order.type_name = self.env._("Subscription")
            elif order.subscription_state == "7_upsell":
                order.type_name = self.env._("Quotation")
            elif order.subscription_state == "2_renewal":
                order.type_name = self.env._("Renewal Quotation")
            else:
                other_orders |= order

        super(SaleOrder, other_orders)._compute_type_name()

    @api.depends("rating_percentage_satisfaction")
    def _compute_percentage_satisfaction(self) -> None:
        for subscription in self:
            subscription.percentage_satisfaction = int(
                subscription.rating_percentage_satisfaction
            )

    @api.depends("starred_user_ids")
    @api.depends_context("uid")
    def _compute_starred(self) -> None:
        for subscription in self:
            subscription.starred = self.env.user in subscription.starred_user_ids

    def _inverse_starred(self) -> None:
        starred_subscriptions = not_star_subscriptions = self.env["sale.order"].sudo()
        for subscription in self:
            if self.env.user in subscription.starred_user_ids:
                starred_subscriptions |= subscription
            else:
                not_star_subscriptions |= subscription
        not_star_subscriptions.write({"starred_user_ids": [Command.link(self.env.uid)]})
        starred_subscriptions.write(
            {"starred_user_ids": [Command.unlink(self.env.uid)]}
        )

    @api.depends("subscription_state", "state", "is_subscription", "amount_untaxed")
    def _compute_recurring_monthly(self) -> None:
        for order in self:
            if order.is_subscription or order.subscription_state == "7_upsell":
                order.recurring_monthly = sum(
                    order.line_ids.mapped("recurring_monthly")
                )
                continue
            order.recurring_monthly = 0

    @api.depends(
        "subscription_state",
        "state",
        "is_subscription",
        "line_ids.price_subtotal",
        "currency_id",
        "company_id",
    )
    def _compute_recurring_total(self) -> None:
        for order in self:
            if order.is_subscription or order.subscription_state == "7_upsell":
                AccountTax = self.env["account.tax"]
                order_lines = order.line_ids.filtered(
                    lambda x: x.recurring_invoice and not x.display_type
                )
                base_lines = [
                    line._prepare_base_line_for_taxes_computation()
                    for line in order_lines
                ]
                AccountTax._add_tax_details_in_base_lines(base_lines, order.company_id)
                AccountTax._round_base_lines_tax_details(base_lines, order.company_id)
                tax_totals = AccountTax._get_tax_totals_summary(
                    base_lines=base_lines,
                    currency=order.currency_id or order.company_id.currency_id,
                    company=order.company_id,
                )
                order.recurring_total = tax_totals["base_amount_currency"]
                continue
            order.recurring_total = 0

    @api.depends("amount_untaxed", "recurring_total")
    def _compute_non_recurring_total(self) -> None:
        for order in self:
            order.non_recurring_total = order.amount_untaxed - order.recurring_total

    @api.depends("is_subscription", "recurring_total")
    def _compute_recurring_details(self) -> None:
        subscription_orders = self.filtered(
            lambda sub: sub.is_subscription or sub.subscription_id
        )
        self.recurring_details = ""
        if subscription_orders.ids:
            for so in subscription_orders:
                lang_code = so.partner_id.lang
                recurring_amount = so.recurring_total
                non_recurring_amount = so.amount_untaxed - recurring_amount
                recurring_formatted_amount = (
                    so.currency_id
                    and format_amount(
                        self.env, recurring_amount, so.currency_id, lang_code
                    )
                ) or recurring_amount
                non_recurring_formatted_amount = (
                    so.currency_id
                    and format_amount(
                        self.env, non_recurring_amount, so.currency_id, lang_code
                    )
                ) or non_recurring_amount
                rendering_values = [
                    {
                        "non_recurring": non_recurring_formatted_amount,
                        "recurring": recurring_formatted_amount,
                    }
                ]
                so.recurring_details = self.env["ir.qweb"]._render(
                    "sale_subscription.recurring_details",
                    {"rendering_values": rendering_values},
                )

    @api.depends("is_subscription", "subscription_state")
    def _compute_access_url(self):
        super()._compute_access_url()
        for order in self:
            if (
                order.is_subscription
                and order.subscription_state
                in SUBSCRIPTION_PROGRESS_STATE + SUBSCRIPTION_CLOSED_STATE
                and not self.env.context.get("force_sale_url")
            ):
                order.access_url = "/my/subscriptions/%s" % order.id

    def _compute_start_date(self) -> None:
        for so in self:
            if not so.is_subscription:
                so.start_date = False
            elif not so.start_date:
                so.start_date = fields.Date.today()

    @api.depends("origin_order_id.start_date", "origin_order_id", "start_date")
    def _compute_first_contract_date(self) -> None:
        for so in self:
            if so.origin_order_id:
                so.first_contract_date = so.origin_order_id.start_date
            else:
                so.first_contract_date = so.start_date

    @api.depends("next_invoice_date", "plan_id")
    def _compute_warn_system_closing(self) -> None:
        for order in self:
            auto_close_limit = order.plan_id.auto_close_limit or 15
            order.warn_system_closing = (
                order.subscription_state == "3_progress"
                and order.next_invoice_date
                and order.next_invoice_date + relativedelta(days=auto_close_limit)
                <= fields.Date.today()
            )

    @api.depends("next_invoice_date", "end_date", "subscription_state")
    def _compute_is_closing(self) -> None:
        for order in self:
            order.is_closing = (
                order.subscription_state in SUBSCRIPTION_PROGRESS_STATE
                and order.user_closable
                and order.end_date
                and order.next_invoice_date
                and order.end_date <= order.next_invoice_date
            )

    @api.depends(
        "subscription_child_ids",
        "origin_order_id",
        "subscription_invoice_line_ids.move_id",
        "subscription_child_ids.subscription_invoice_line_ids.move_id",
    )
    def _compute_invoices(self):
        subscription_ids = []
        so_by_origin = defaultdict(lambda: self.env["sale.order"])
        parent_order_ids = []
        for order in self:
            if order.is_subscription and order.id:
                subscription_ids.append(order.id)
                origin_key = (
                    order.origin_order_id.id if order.origin_order_id else order.id
                )
                parent_order_ids.append(origin_key)
                so_by_origin[origin_key] += order

        subscriptions = self.browse(subscription_ids)
        res = super(SaleOrder, self - subscriptions)._compute_invoices()
        if not subscriptions:
            return res
        subscriptions.update({"invoice_ids": [], "invoice_count": 0})

        if not so_by_origin or not subscription_ids:
            return res

        self.flush_recordset(fnames=["origin_order_id"])
        all_subscription_ids = (
            self.search([("origin_order_id", "in", parent_order_ids)]).ids
            + parent_order_ids
        )

        subscription_move_lines = self.env["account.move.line"].search(
            [("subscription_id", "in", all_subscription_ids)]
        )
        subscription_move_lines.fetch(["subscription_id", "move_id"])
        subscription_move_lines.subscription_id.fetch(["origin_order_id"])
        move_by_origin = defaultdict(list)
        for aml in subscription_move_lines:
            origin_order = (
                aml.subscription_id.origin_order_id.id or aml.subscription_id.id
            )
            move_by_origin[origin_order].append(aml.move_id.id)

        query = """
            SELECT COALESCE(origin_order_id, so.id),
                   array_agg(DISTINCT am.id) AS move_ids
              FROM sale_order so
              JOIN sale_order_line sol ON sol.order_id = so.id
              JOIN account_move_line_sale_order_line_rel solam ON sol.id = solam.order_line_id
              JOIN account_move_line aml ON aml.id = solam.move_line_id
              JOIN account_move am ON am.id = aml.move_id
             WHERE am.company_id = ANY(%s)
               AND so.id = ANY(%s)
               AND am.move_type IN ('out_invoice', 'out_refund')
          GROUP BY COALESCE(origin_order_id, so.id)
        """

        self.env.cr.execute(
            query, [list(self.env.companies.ids), list(all_subscription_ids)]
        )
        orders_vals = self.env.cr.fetchall()
        for origin_order_id, invoices_ids in orders_vals + list(move_by_origin.items()):
            other_move_ids = move_by_origin[origin_order_id]
            all_move_ids = set(invoices_ids + other_move_ids)
            all_move_ids = (
                self.env["account.move"]
                .browse(all_move_ids)
                ._filtered_access("read")
                .ids
            )
            so_by_origin[origin_order_id].update(
                {
                    "invoice_ids": [Command.set(all_move_ids)],
                    "invoice_count": len(all_move_ids),
                }
            )
        return res

    @api.depends("is_subscription", "state", "start_date", "subscription_state")
    def _compute_next_invoice_date(self) -> None:
        for so in self:
            if not so.is_subscription and so.subscription_state != "7_upsell":
                so.next_invoice_date = False
            elif not so.next_invoice_date and so.state == "done":
                so.next_invoice_date = so.start_date or fields.Date.today()

    @api.depends("start_date", "state", "next_invoice_date")
    def _compute_last_invoice_date(self) -> None:
        for order in self:
            last_date = (
                order.next_invoice_date
                and order.plan_id.billing_period
                and order.next_invoice_date - order.plan_id.billing_period
            )
            start_date = order.start_date or fields.Date.today()
            if order.state == "done" and last_date and last_date >= start_date:
                order.last_invoice_date = last_date
            else:
                order.last_invoice_date = False

    @api.depends("subscription_child_ids")
    def _compute_renewal_count(self) -> None:
        self.renewal_count = 0
        if not any(self.mapped("subscription_state")):
            return
        result = self.env["sale.order"]._read_group(
            [
                ("subscription_state", "=", "2_renewal"),
                ("state", "in", ["draft", "sent"]),
                ("subscription_id", "in", self.ids),
            ],
            ["subscription_id"],
            ["__count"],
        )
        counters = {subscription.id: count for subscription, count in result}
        for so in self:
            so.renewal_count = counters.get(so.id, 0)

    @api.depends("subscription_child_ids")
    def _compute_upsell_count(self) -> None:
        self.upsell_count = 0
        if not any(self.mapped("subscription_state")):
            return
        result = self.env["sale.order"]._read_group(
            [
                ("subscription_state", "=", "7_upsell"),
                ("state", "in", ["draft", "sent"]),
                ("subscription_id", "in", self.ids),
            ],
            ["subscription_id"],
            ["__count"],
        )
        counters = {subscription.id: count for subscription, count in result}
        for so in self:
            so.upsell_count = counters.get(so.id, 0)

    @api.depends("origin_order_id")
    def _compute_history_count(self) -> None:
        if not any(self.mapped("subscription_state")):
            self.history_count = 0
            return
        origin_ids = self.origin_order_id.ids + self.ids
        result = self.env["sale.order"]._read_group(
            [
                ("state", "not in", ["cancel", "draft"]),
                ("origin_order_id", "in", origin_ids),
            ],
            ["origin_order_id"],
            ["__count"],
        )
        counters = {origin_order.id: count + 1 for origin_order, count in result}
        for so in self:
            so.history_count = counters.get(so.origin_order_id.id or so.id, 0)

    @api.depends("is_subscription", "subscription_state")
    def _compute_origin_order_id(self) -> None:
        for order in self:
            if (
                order.is_subscription or order.subscription_state == "7_upsell"
            ) and not order.origin_order_id:
                order.origin_order_id = (
                    order.subscription_id.origin_order_id or order.subscription_id
                )

    def _track_subtype(self, init_values):
        self.check_singleton()
        if "subscription_state" in init_values:
            return self.env.ref("sale_subscription.subtype_state_change")
        if (
            self.is_subscription
            and "next_invoice_date" in init_values
            and self.env.context.get("subscription_pause")
        ):
            return self.env.ref(
                "sale_subscription.subtype_resume_and_pause_subscription"
            )
        return super()._track_subtype(init_values)

    @api.depends("template_id")
    def _compute_plan_id(self) -> None:
        for order in self:
            order.plan_id = None
            if order.template_id and order.template_id.plan_id:
                order.plan_id = order.template_id.plan_id

    @api.depends(
        "subscription_child_ids.subscription_state", "subscription_child_ids.state"
    )
    def _compute_is_renewing(self) -> None:
        for order in self:
            order.is_renewing = any(
                child.subscription_state == "2_renewal"
                and child.state in ("draft", "sent")
                for child in order.subscription_child_ids
            )

    @api.depends(
        "subscription_child_ids.subscription_state", "subscription_child_ids.state"
    )
    def _compute_is_upselling(self) -> None:
        for order in self:
            order.is_upselling = any(
                child.subscription_state == "7_upsell"
                and child.state in ("draft", "sent")
                for child in order.subscription_child_ids
            )

    @api.depends("subscription_state", "next_invoice_date")
    def _compute_display_late(self) -> None:
        today = fields.Date.today()
        for order in self:
            order.display_late = (
                order.subscription_state in SUBSCRIPTION_PROGRESS_STATE
                and order.next_invoice_date
                and order.next_invoice_date < today
            )

    @api.depends("line_ids", "line_ids.recurring_invoice")
    def _compute_has_recurring_line(self) -> None:
        recurring_product_orders = self.env["sale.order"]
        one_time_order_ids = [
            so.id for so in self if so._subscription_is_one_time_sale()
        ]
        for line in self.line_ids:
            if line.product_id.recurring_invoice and (
                line.order_id.plan_id or line.order_id.id not in one_time_order_ids
            ):
                recurring_product_orders |= line.order_id
        recurring_product_orders.has_recurring_line = True
        (self - recurring_product_orders).has_recurring_line = False

    @api.depends("subscription_id")
    def _compute_note_order(self) -> None:
        for order in self:
            if order.internal_note or not order.subscription_id:
                order.note_order = order
            else:
                order.note_order = order.subscription_id.note_order

    def _search_note_order(self, operator, value):
        if operator != "in":
            return NotImplemented
        origin_orders = self.search_fetch(
            [("id", operator, value)], ["origin_order_id"], order="id"
        )
        ooids = [oo.origin_order_id.id or oo.id for oo in origin_orders]
        return [("origin_order_id", "in", ooids), ("internal_note", "=", False)]

    @api.depends("note_order.internal_note")
    def _compute_internal_note_display(self) -> None:
        for order in self:
            order.internal_note_display = order.note_order.internal_note

    def _inverse_internal_note_display(self) -> None:
        for order in self:
            order.note_order.internal_note = order.internal_note_display

    def _mail_track(self, tracked_fields, initial_values):
        res = super()._mail_track(tracked_fields, initial_values)
        if self.is_subscription:
            self.env["sale.order.log"]._create_log(self, initial_values.copy())
        return res

    def _prepare_invoice_vals(self):
        vals = super()._prepare_invoice_vals()
        if self.template_id.journal_id:
            vals["journal_id"] = self.template_id.journal_id.id
        return vals

    def _notify_thread(self, message, msg_vals=False, **kwargs):
        if not kwargs.get("model_description") and self.is_subscription:
            kwargs["model_description"] = self.env._("Subscription")
        super()._notify_thread(message, msg_vals=msg_vals, **kwargs)

    def _get_duplicate_orders(self) -> dict:
        non_renewal_upsell_orders = self.filtered_domain(
            [("subscription_state", "not in", ("2_renewal", "7_upsell"))]
        )
        return super(SaleOrder, non_renewal_upsell_orders)._get_duplicate_orders()

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        for order, vals in zip(orders, vals_list, strict=False):
            if order.is_subscription and not order.subscription_state:
                order.subscription_state = vals.get("subscription_state", "1_draft")
        return orders

    def write(self, vals):
        new_user_id = vals.get("user_id")
        valid_state_update = (
            vals.get("subscription_state") in SUBSCRIPTION_PROGRESS_STATE
        )
        res = super().write(vals)
        if "start_date" in vals:
            self.filtered(
                lambda so: so.subscription_state == "7_upsell"
            ).line_ids._apply_upsell_prorata_discount()
        if new_user_id or valid_state_update:
            for order in self:
                if (
                    not order.is_subscription
                    or order.subscription_state not in SUBSCRIPTION_PROGRESS_STATE
                ):
                    continue
                current_partner_user = order.partner_id.user_id
                subscription_user = order.user_id
                if subscription_user != current_partner_user:
                    partner_to_remove = (
                        current_partner_user.partner_id - order.partner_id
                    )
                    order.message_unsubscribe(partner_ids=partner_to_remove.ids)
                    order.partner_id.sudo().user_id = subscription_user
        for order in self:
            if (
                order.subscription_state == "7_upsell"
                and order.state in ["draft", "sent"]
                and ("start_date" in vals or "next_invoice_date" in vals)
            ):
                ratio = order._get_ratio_value()
                line_to_discount, discount_comment = (
                    order.line_ids._get_renew_discount_info(upsell_ratio=ratio)
                )
                line_to_discount._create_update_subscription_discount_values(
                    updell_ratio=ratio, discount_comment=discount_comment
                )
        return res

    @api.ondelete(at_uninstall=False)
    def _unlink_except_draft_or_cancel(self):
        for order in self:
            if (
                order.state not in ["draft", "sent"]
                and order.subscription_state
                and order.subscription_state
                not in SUBSCRIPTION_DRAFT_STATE + SUBSCRIPTION_CLOSED_STATE
            ):
                raise UserError(
                    self.env._(
                        "Oops! Before you can delete a confirmed subscription, you'll need to close and cancel it."
                    )
                )
        return super()._unlink_except_draft_or_cancel()

    def copy_data(self, default=None):
        default = dict(default or {})
        vals_list = super().copy_data(default=default)
        for order, vals in zip(self, vals_list, strict=False):
            if order.subscription_state == "7_upsell":
                vals.update(
                    {
                        "client_order_ref": order.client_order_ref,
                        "subscription_id": order.subscription_id.id,
                        "origin_order_id": order.origin_order_id.id,
                        "subscription_state": "7_upsell",
                    }
                )
            elif (not order.subscription_state and order.plan_id) or (
                order.subscription_state and "subscription_state" not in default
            ):
                vals.update({"subscription_state": "1_draft"})
        return vals_list

    def get_future_next_invoice_date(self):
        self.check_singleton()
        return (
            self.next_invoice_date + self.plan_id.billing_period - relativedelta(days=1)
        )

    def action_update_prices(self):
        self.line_ids.price_unit = False
        super().action_update_prices()

    def action_draft(self):
        for order in self:
            if (
                order.state == "cancel"
                and order.is_subscription
                and any(
                    state in ["draft", "posted"]
                    for state in order.line_ids.invoice_line_ids.move_id.mapped("state")
                )
            ):
                raise UserError(
                    self.env._(
                        "You cannot set to draft a cancelled quotation linked to invoiced subscriptions. Please create a new quotation."
                    )
                )
        res = super().action_draft()
        for order in self:
            if order.is_subscription:
                order.subscription_state = (
                    "2_renewal" if order.subscription_id else "1_draft"
                )
        return res

    def _action_cancel(self):
        to_open_ids = []
        for order in self:
            related_move = order._get_subscription_invoices()
            if order.subscription_state == "7_upsell":
                if order.state == "done":
                    cancel_message_body = self.env._(
                        "The upsell %s has been cancelled. Please recheck the quantities as they may have been affected by this cancellation.",
                        order._get_html_link(),
                    )
                else:
                    cancel_message_body = self.env._(
                        "The upsell %s has been cancelled.", order._get_html_link()
                    )
                order.subscription_id.message_post(body=cancel_message_body)
            elif order.subscription_state == "2_renewal":
                cancel_message_body = self.env._(
                    "The renewal %s has been cancelled.", order._get_html_link()
                )
                order.subscription_id.message_post(body=cancel_message_body)
            elif (
                order.subscription_state
                in SUBSCRIPTION_PROGRESS_STATE + SUBSCRIPTION_DRAFT_STATE
                and not any(
                    state in ["draft", "posted"]
                    for state in related_move.mapped("state")
                )
            ):
                parent_last_log = (
                    order.subscription_id
                    and order.subscription_id.order_log_ids.sorted(
                        lambda log: (log.event_date, log.id), reverse=True
                    )[:1]
                )
                if (
                    parent_last_log
                    and parent_last_log.event_type == "3_transfer"
                    and parent_last_log.amount_signed <= 0
                ):
                    to_open_ids.append(order.subscription_id.id)
                    parent_link = order.subscription_id._get_html_link()
                    cancel_activity_body = self.env._(
                        """Subscription %(link)s has been cancelled. The parent order %(parent_link)s has been reopened.
                                                You should close %(parent_link)s if the customer churned, or renew it if the customer continue the service.
                                                Note: if you already created a new subscription instead of renewing it, please cancel your newly
                                                created subscription and renew %(parent_link)s instead""",
                        link=order._get_html_link(),
                        parent_link=parent_link,
                    )
                    order.activity_schedule(
                        "mail.mail_activity_data_todo",
                        summary=self.env._("Check reopened subscription"),
                        note=cancel_activity_body,
                        user_id=order.subscription_id.user_id.id,
                    )
                order.subscription_state = False
            elif order.subscription_state in SUBSCRIPTION_PROGRESS_STATE + [
                "5_renewed"
            ]:
                raise ValidationError(
                    self.env._(
                        "Cancelling an invoiced subscription wouldn't be fair to the customer. "
                        "Once the invoice been created and possibly even paid, it's a done deal. Cancelling the subscription would definitely cause some chaos!"
                    )
                )
            elif order.subscription_id and order.subscription_state == "6_churn":
                raise ValidationError(
                    self.env._("You cannot cancel a churned renewed subscription.")
                )
            if order.is_subscription:
                order.subscription_state = False
        res = super()._action_cancel()
        self.browse(to_open_ids).set_open()
        return res

    def _prepare_confirmation_values(self):
        values = super()._prepare_confirmation_values()
        if all(self.mapped("is_subscription")):
            values["subscription_state"] = "3_progress"
        return values

    def action_confirm(self):
        recurring_order = self.env["sale.order"]
        upsell = self.env["sale.order"]
        renewal = self.env["sale.order"]
        post_paid = self.env["sale.order"]

        with self.env.protecting([self.line_ids._fields["discount"]], self.line_ids):
            for order in self:
                if order.subscription_id:
                    if order.subscription_state == "7_upsell" and order.state in [
                        "draft",
                        "sent",
                    ]:
                        upsell |= order
                    elif order.subscription_state == "2_renewal":
                        renewal |= order
                if order.is_subscription:
                    recurring_order |= order
                    if not order.subscription_state:
                        order.subscription_state = "1_draft"
                elif order.subscription_state != "7_upsell":
                    order.subscription_state = False
                if order.line_ids._is_all_postpaid():
                    post_paid |= order

            _debug.pipeline(
                "subscription_confirm",
                orders=self,
                recurring=recurring_order,
                upsell=upsell,
                renewal=renewal,
                postpaid=post_paid,
            )
            res_sub = super(SaleOrder, recurring_order).action_confirm()
            res_other = super(SaleOrder, self - recurring_order).action_confirm()
            recurring_order._confirm_subscription()
            renewal._confirm_renewal()
            upsell._confirm_upsell()
            post_paid._update_next_invoice_date()

        return res_sub and res_other

    def action_send_quotation(self):
        if len(self) == 1:
            has_recurring_line = self.line_ids.filtered(
                lambda l: l.product_id.recurring_invoice
            )
            if (
                not self._subscription_is_one_time_sale()
                and self.has_recurring_line
                and not self.plan_id
            ):
                raise UserError(
                    self.env._(
                        "Please set a recurring plan on the subscription before sending the email."
                    )
                )
            if self.plan_id and not has_recurring_line:
                raise UserError(
                    self.env._(
                        "Please remove the recurring plan on the subscription before sending the email."
                    )
                )
        return super().action_send_quotation()

    def action_preview_sale_order(self):
        self.check_singleton()
        if (
            not self._subscription_is_one_time_sale()
            and self.has_recurring_line
            and not self.plan_id
        ):
            raise UserError(
                self.env._(
                    "Please add a recurring plan on the subscription or remove the recurring product."
                )
            )
        if self.plan_id and not self.has_recurring_line:
            raise UserError(
                self.env._(
                    "Please add a recurring product in the subscription or remove the recurring plan."
                )
            )
        return super().action_preview_sale_order()

    def _confirm_subscription(self) -> None:
        today = fields.Date.today()
        for sub in self:
            sub._portal_get_or_create_token()
            if not sub.start_date:
                sub.start_date = today
            if sub.plan_id.repeat_interval <= 0:
                raise UserError(
                    self.env._(
                        "Recurring period must be a positive number. Please ensure the input is a valid positive numeric value."
                    )
                )
            sub._set_deferred_end_date_from_template()
            sub.line_ids._reset_subscription_qty_to_invoice()
            if sub._check_token_saving_conditions():
                sub._save_token_from_payment()

    def _set_deferred_end_date_from_template(self) -> None:
        self.check_singleton()
        if self.template_id and not self.template_id.is_unlimited and not self.end_date:
            self.write(
                {
                    "end_date": self.start_date
                    + self.template_id.duration
                    - relativedelta(days=1)
                }
            )

    def _confirm_upsell(self) -> None:
        today = fields.Date.today()
        for so in self:
            if (so.start_date or today) >= so.subscription_id.next_invoice_date:
                _debug.logic(
                    "upsell_refused",
                    order=so,
                    subscription=so.subscription_id,
                    reason="next_invoice_date_in_the_past",
                )
                raise ValidationError(
                    self.env._(
                        "You cannot upsell a subscription whose next invoice date is in the past.\n"
                        "Please, invoice directly the %s contract.",
                        so.subscription_id.name,
                    )
                )
        existing_line_ids = self.subscription_id.line_ids
        _dummy, update_values = self.update_existing_subscriptions()
        updated_line_ids = self.env["sale.order.line"].browse(
            {val[1] for val in update_values}
        )
        new_lines_ids = self.subscription_id.line_ids - existing_line_ids
        self.env["sale.order"].search(
            [
                ("subscription_state", "=", "7_upsell"),
                ("state", "in", ["draft", "sent"]),
                ("subscription_id", "in", self.subscription_id.ids),
                ("id", "not in", self.ids),
            ]
        ).action_cancel()
        for upsell in self:
            upsell.subscription_id.message_post(
                body=self.env._(
                    "The upsell %s has been confirmed.", upsell._get_html_link()
                )
            )
        _debug.pipeline(
            "upsell_confirmed",
            orders=self,
            updated_lines=updated_line_ids,
            new_lines=new_lines_ids,
        )
        for line in (updated_line_ids | new_lines_ids).with_context(
            skip_line_status_compute=True
        ):
            line.qty_to_invoice = 0
            line.qty_invoiced = line.product_qty
            line.invoice_state = "no"

    def _confirm_renewal(self):
        today = fields.Date.today()
        for renew in self:
            parent = renew.subscription_id
            if renew.start_date < parent.next_invoice_date:
                _debug.logic("renewal_refused", order=renew, reason="starts_too_early")
                raise ValidationError(
                    self.env._(
                        "You cannot validate a renewal quotation starting before the next invoice date "
                        "of the parent contract. Please update the start date after the %s.",
                        format_date(self.env, parent.next_invoice_date),
                    )
                )
            if parent.start_date == parent.next_invoice_date:
                _debug.logic(
                    "renewal_refused", order=renew, reason="parent_never_invoiced"
                )
                raise ValidationError(
                    self.env._(
                        "You can not upsell or renew a subscription that has not been invoiced yet. "
                        "Please, update directly the %s contract or invoice it first.",
                        parent.name,
                    )
                )
            if parent.subscription_state == "5_renewed":
                _debug.logic(
                    "renewal_refused", order=renew, reason="parent_already_renewed"
                )
                raise ValidationError(
                    self.env._(
                        "You cannot renew a subscription that has been renewed. "
                    )
                )
            if self.search_count(
                [
                    ("origin_order_id", "=", renew.origin_order_id.id),
                    ("subscription_state", "in", SUBSCRIPTION_PROGRESS_STATE),
                    ("id", "not in", [parent.id, renew.id]),
                ],
                limit=1,
            ):
                _debug.logic("renewal_refused", order=renew, reason="active_sibling")
                raise ValidationError(
                    self.env._(
                        "You cannot renew a contract that already has an active subscription. "
                    )
                )
            other_renew_so_ids = (
                parent.subscription_child_ids.filtered(
                    lambda so: (
                        so.subscription_state == "2_renewal" and so.state != "cancel"
                    )
                )
                - renew
            )
            if other_renew_so_ids:
                other_renew_so_ids._action_cancel()

            renew_msg_body = self.env._(
                "This subscription is renewed in %s with a change of plan.",
                renew._get_html_link(),
            )
            parent.message_post(body=renew_msg_body)
            renew_close_reason_id = self.env.ref("sale_subscription.close_reason_renew")
            end_of_contract_reason_id = self.env.ref(
                "sale_subscription.close_reason_end_of_contract"
            )
            close_reason_id = (
                renew_close_reason_id
                if parent.subscription_state != "6_churn"
                else end_of_contract_reason_id
            )
            parent.set_close(close_reason_id=close_reason_id.id, renew=True)
            start_date = renew.start_date or parent.next_invoice_date
            renew.write({"date_order": today, "start_date": start_date})
            if renew._check_token_saving_conditions():
                renew._save_token_from_payment()

    def _check_token_saving_conditions(self):
        self.check_singleton()
        last_transaction = self.sudo().transaction_ids._get_last()
        last_token = last_transaction.token_id
        subscription_fully_paid = (
            self.currency_id.compare_amounts(last_transaction.amount, self.amount_total)
            >= 0
        )
        transaction_authorized = (
            last_transaction and last_transaction.renewal_state == "authorized"
        )
        return (
            last_token
            and last_transaction
            and subscription_fully_paid
            and transaction_authorized
        )

    def _save_token_from_payment(self) -> None:
        self.check_singleton()
        last_token = self.sudo().transaction_ids._get_last().token_id.id
        if last_token:
            self.payment_token_id = last_token

    def _group_expand_states(self, states, domain):
        return sorted(set(states).union({"3_progress", "4_paused"}))

    @api.model
    def _get_associated_so_action(self) -> dict:
        return {
            "type": "ir.actions.act_window",
            "res_model": "sale.order",
            "views": [
                [
                    self.env.ref("sale_subscription.sale_subscription_view_tree").id,
                    "list",
                ],
                [
                    self.env.ref(
                        "sale_subscription.sale_subscription_primary_form_view"
                    ).id,
                    "form",
                ],
                [False, "kanban"],
                [False, "calendar"],
                [False, "pivot"],
                [False, "graph"],
            ],
        }

    def open_subscription_history(self):
        self.check_singleton()
        action = {
            "type": "ir.actions.act_window",
            "res_model": "sale.order",
            "views": [
                [
                    self.env.ref(
                        "sale_subscription.sale_subscription_quotation_tree_view"
                    ).id,
                    "list",
                ],
                [
                    self.env.ref(
                        "sale_subscription.sale_subscription_primary_form_view"
                    ).id,
                    "form",
                ],
            ],
        }
        origin_order_id = self.origin_order_id.id or self.id
        action["name"] = self.env._("History")
        action["domain"] = [
            ("state", "not in", ["cancel", "draft"]),
            "|",
            ("id", "=", origin_order_id),
            ("origin_order_id", "=", origin_order_id),
        ]
        action["context"] = {
            **action.get("context", {}),
            "create": False,
        }
        return action

    def open_subscription_renewal(self):
        self.check_singleton()
        action = self._get_associated_so_action()
        action["name"] = self.env._("Renewal Quotations")
        renewal = self.subscription_child_ids.filtered(
            lambda so: so.subscription_state == "2_renewal"
        )
        if len(renewal) == 1:
            action["res_id"] = renewal.id
            action["views"] = [
                (
                    self.env.ref(
                        "sale_subscription.sale_subscription_primary_form_view"
                    ).id,
                    "form",
                )
            ]
        else:
            action["domain"] = [
                ("subscription_id", "=", self.id),
                ("subscription_state", "=", "2_renewal"),
                ("state", "in", ["draft", "sent"]),
            ]
            action["views"] = [
                (self.env.ref("sale.view_sale_order_list_quotation").id, "list"),
                (
                    self.env.ref(
                        "sale_subscription.sale_subscription_primary_form_view"
                    ).id,
                    "form",
                ),
            ]

        action["context"] = {
            **action.get("context", {}),
            "create": False,
        }
        return action

    def open_subscription_upsell(self):
        self.check_singleton()
        action = self._get_associated_so_action()
        action["name"] = self.env._("Upsell Quotations")
        upsell = self.subscription_child_ids.filtered(
            lambda so: (
                so.subscription_state == "7_upsell" and so.state in ["draft", "sent"]
            )
        )
        if len(upsell) == 1:
            action["res_id"] = upsell.id
            action["views"] = [
                (
                    self.env.ref(
                        "sale_subscription.sale_subscription_primary_form_view"
                    ).id,
                    "form",
                )
            ]
        else:
            action["domain"] = [
                ("subscription_id", "=", self.id),
                ("subscription_state", "=", "7_upsell"),
                ("state", "in", ["draft", "sent"]),
            ]
            action["views"] = [
                (self.env.ref("sale.view_sale_order_list_quotation").id, "list"),
                (
                    self.env.ref(
                        "sale_subscription.sale_subscription_primary_form_view"
                    ).id,
                    "form",
                ),
            ]
        action["context"] = {
            **action.get("context", {}),
            "create": False,
        }
        return action

    def action_sale_order_log(self):
        self.check_singleton()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "sale_subscription.sale_order_log_analysis_action"
        )
        origin_order_ids = self.origin_order_id.ids + self.ids
        genealogy_orders_ids = self.search(
            [
                "|",
                ("id", "in", origin_order_ids),
                ("origin_order_id", "in", origin_order_ids),
            ]
        )
        action.update(
            {
                "name": self.env._("MRR changes"),
                "domain": [("order_id", "in", genealogy_orders_ids.ids)],
            }
        )
        return action

    def _create_renew_upsell_order(self, subscription_state, message_body):
        self.check_singleton()
        if self.start_date == self.next_invoice_date:
            raise ValidationError(
                self.env._(
                    "You can not upsell or renew a subscription that has not been invoiced yet. "
                    "Please, update directly the %s contract or invoice it first.",
                    self.name,
                )
            )
        values = self._prepare_upsell_renew_order_values(subscription_state)
        order = self.env["sale.order"].create(values)
        self._subscribe_followers_to_new_order(order)
        self.subscription_child_ids = [Command.link(order.id)]
        order.message_post(body=message_body)
        if subscription_state == "7_upsell":
            parent_message_body = self.env._(
                "An upsell quotation %s has been created", order._get_html_link()
            )
        else:
            parent_message_body = self.env._(
                "A renewal quotation %s has been created", order._get_html_link()
            )
        self.message_post(body=parent_message_body)
        order.line_ids._compute_tax_ids()
        return order

    def _prepare_renew_upsell_order(self, subscription_state, message_body):
        order = self._create_renew_upsell_order(subscription_state, message_body)
        action = self._get_associated_so_action()
        action["name"] = (
            self.env._("Upsell")
            if subscription_state == "7_upsell"
            else self.env._("Renew")
        )
        action["views"] = [
            (
                self.env.ref(
                    "sale_subscription.sale_subscription_primary_form_view"
                ).id,
                "form",
            )
        ]
        action["res_id"] = order.id
        return action

    def _get_order_digest(
        self, origin="", template="sale_subscription.sale_order_digest", lang=None
    ):
        self.check_singleton()
        values = {
            "origin": origin,
            "record_url": self._get_html_link(),
            "start_date": self.start_date,
            "next_invoice_date": self.next_invoice_date,
            "recurring_monthly": self.recurring_monthly,
            "untaxed_amount": self.amount_untaxed,
            "quotation_template": self.template_id.name,
        }
        return self.env["ir.qweb"].with_context(lang=lang)._render(template, values)

    def prepare_renewal_order(self):
        self.check_singleton()
        lang = self.partner_id.lang or self.env.user.lang
        renew_msg_body = self._get_order_digest(origin="renewal", lang=lang)
        return self._prepare_renew_upsell_order("2_renewal", renew_msg_body)

    def prepare_upsell_order(self):
        self.check_singleton()
        lang = self.partner_id.lang or self.env.user.lang
        upsell_msg_body = self._get_order_digest(origin="upsell", lang=lang)
        return self._prepare_renew_upsell_order("7_upsell", upsell_msg_body)

    def reopen_order(self) -> None:
        if self and set(self.mapped("subscription_state")) != {"6_churn"}:
            raise UserError(
                self.env._("You cannot reopen a subscription that isn't closed.")
            )
        self.set_open()

    def pause_subscription(self) -> None:
        with self.env.protecting([self.line_ids._fields["discount"]], self.line_ids):
            self.filtered(lambda so: so.subscription_state == "3_progress").write(
                {"subscription_state": "4_paused"}
            )

    def resume_subscription(self) -> None:
        with self.env.protecting([self.line_ids._fields["discount"]], self.line_ids):
            self.filtered(lambda so: so.subscription_state == "4_paused").write(
                {"subscription_state": "3_progress"}
            )

    def create_alternative(self):
        self.check_singleton()
        alternative_so = self.copy(
            {
                "origin_order_id": self.origin_order_id.id,
                "subscription_id": self.subscription_id.id,
                "subscription_state": self.env.context.get(
                    "default_subscription_state", "2_renewal"
                ),
                "next_invoice_date": self.next_invoice_date,
            }
        )
        action = alternative_so._get_associated_so_action()
        action["views"] = [
            (
                self.env.ref(
                    "sale_subscription.sale_subscription_primary_form_view"
                ).id,
                "form",
            )
        ]
        action["res_id"] = alternative_so.id
        return action

    def _is_lock_required(self) -> bool:
        self.check_singleton()
        should_lock = super()._is_lock_required()
        return bool(should_lock and not self.is_subscription)

    def _upsell_context(self):
        return {"skip_next_invoice_update": True}

    def update_existing_subscriptions(self) -> tuple:
        create_values, update_values = [], []
        context = self._upsell_context()
        for order in self:
            create_values, update_values = order.line_ids.filtered(
                lambda sol: not sol.display_type
            )._subscription_update_line_data(order.subscription_id)
            order.subscription_id.with_context(**context).write(
                {"line_ids": create_values + update_values}
            )
        return create_values, update_values

    def _get_closing_end_date(self, renew=False):
        self.check_singleton()
        end_date = fields.Date.context_today(self)
        if self.end_date and self.end_date <= end_date:
            end_date = self.end_date
        elif (
            self.plan_id.user_closable
            and self.plan_id.user_closable_options == "end_of_period"
            and self.env.context.get("allow_future_end_date")
        ):
            end_date = self.next_invoice_date - relativedelta(days=1)
        elif renew:
            end_date = self.next_invoice_date
        return end_date

    def _set_closed_state(self, renew=False) -> None:
        renewal_order = self.subscription_child_ids.filtered(
            lambda s: s.subscription_state in SUBSCRIPTION_PROGRESS_STATE
        )
        if renew and renewal_order and self.state == "done":
            self.subscription_state = "5_renewed"
            self.locked = True
            _debug.lifecycle("subscription_state", subscription=self, state="5_renewed")
        else:
            self.subscription_state = "6_churn"
            _debug.lifecycle("subscription_state", subscription=self, state="6_churn")

    def set_close(self, close_reason_id=None, renew=False):
        today = fields.Date.context_today(self)
        if not close_reason_id:
            renew_close_reason_id = self.env.ref(
                "sale_subscription.close_reason_renew"
            ).id
            end_of_contract_reason_id = self.env.ref(
                "sale_subscription.close_reason_end_of_contract"
            ).id
            close_reason_unknown_id = self.env.ref(
                "sale_subscription.close_reason_unknown"
            ).id
        for sub in self:
            end_date = sub._get_closing_end_date(renew=renew)
            if renew or end_date <= today:
                sub._set_closed_state(renew)
            values = {"end_date": end_date}
            if not close_reason_id and not (close_reason_id := sub.close_reason_id):
                if renew:
                    close_reason_id = renew_close_reason_id
                elif sub.end_date and sub.end_date <= end_date:
                    close_reason_id = end_of_contract_reason_id
                else:
                    close_reason_id = close_reason_unknown_id
            _debug.lifecycle(
                "subscription_closed",
                subscription=sub,
                end_date=end_date,
                renew=renew,
                reason=close_reason_id,
            )
            sub.update(dict(**values, close_reason_id=close_reason_id))
        return True

    def _filtered_reopenable(self, payment_date, reopen_reasons) -> Self:
        return self.filtered(
            lambda sub: (
                sub.subscription_state == "6_churn"
                and sub.close_reason_id in reopen_reasons
                and payment_date - timedelta(days=sub.plan_id.auto_close_limit)
                <= sub.next_invoice_date
            )
        )

    def set_open(self):
        all_origin_order_ids = self.origin_order_id.ids + self.ids
        incompatible_origin = (
            self.env["sale.order"]
            .search(
                [
                    ("origin_order_id", "in", all_origin_order_ids),
                    ("subscription_state", "in", SUBSCRIPTION_PROGRESS_STATE),
                ]
            )
            .origin_order_id
        )
        to_open_ids = []
        for order in self:
            if order.subscription_state == "6_churn" and order.end_date:
                order.end_date = False
                reopen_activity_body = self.env._(
                    "Subscription %s has been reopened. The end date has been removed",
                    order._get_html_link(),
                )
                order.activity_schedule(
                    "mail.mail_activity_data_todo",
                    summary=self.env._("Check reopened subscription"),
                    note=reopen_activity_body,
                    user_id=order.user_id.id,
                )
            if order.is_subscription and not (
                order in incompatible_origin
                or order.origin_order_id in incompatible_origin
            ):
                to_open_ids.append(order.id)
        to_open = self.browse(to_open_ids)
        _debug.lifecycle("subscriptions_reopened", requested=self, reopened=to_open)
        super(
            SaleOrder, to_open.filtered(lambda so: so.state == "cancel")
        ).action_draft()
        to_open.update(
            {
                "state": "done",
                "subscription_state": "3_progress",
                "close_reason_id": False,
                "locked": False,
            }
        )

    @api.model
    def _cron_update_kpi(self) -> None:
        subscriptions = self.search(
            [("subscription_state", "=", "3_progress"), ("is_subscription", "=", True)]
        )
        subscriptions._update_kpi()

    def _prepare_upsell_renew_order_values(self, subscription_state):
        self.check_singleton()
        today = fields.Date.today()
        if (
            subscription_state == "7_upsell"
            and self.next_invoice_date
            and self.next_invoice_date <= max(self.first_contract_date or today, today)
        ):
            raise UserError(
                self.env._(
                    "You cannot create an upsell for this subscription because it :\n"
                    " - Has not started yet.\n"
                    " - Has no invoiced period in the future."
                )
            )
        lang_code = self.partner_id.lang
        subscription = self.with_company(self.company_id)
        order_lines = self.with_context(
            lang=lang_code
        ).line_ids._prepare_renew_upsell_line_commands(subscription_state)
        is_subscription = subscription_state == "2_renewal"
        if subscription_state == "7_upsell":
            start_date = fields.Date.today()
            next_invoice_date = self.next_invoice_date
        else:
            start_date = self.next_invoice_date
            next_invoice_date = self.next_invoice_date
        values = {
            "is_subscription": is_subscription,
            "subscription_id": subscription.id,
            "pricelist_id": subscription.pricelist_id.id,
            "partner_id": subscription.partner_id.id,
            "partner_invoice_id": subscription.partner_invoice_id.id,
            "partner_shipping_id": subscription.partner_shipping_id.id,
            "line_ids": order_lines,
            "subscription_state": subscription_state,
            "origin": subscription.client_order_ref,
            "client_order_ref": subscription.client_order_ref,
            "origin_order_id": subscription.origin_order_id.id,
            "notes": subscription.notes,
            "user_id": subscription.user_id.id,
            "payment_term_id": subscription.payment_term_id.id,
            "company_id": subscription.company_id.id,
            "journal_id": subscription.journal_id.id
            if subscription.journal_id
            else None,
            "template_id": self.template_id.id,
            "payment_token_id": False,
            "start_date": start_date,
            "next_invoice_date": next_invoice_date,
            "plan_id": subscription.plan_id.id,
        }
        if subscription_state == "2_renewal":
            values.update({"tag_ids": subscription.tag_ids.ids})
        return values

    def _update_kpi(self) -> None:
        for subscription in self:
            delta_1month = subscription._get_subscription_delta(
                fields.Date.today() - relativedelta(months=1)
            )
            delta_3months = subscription._get_subscription_delta(
                fields.Date.today() - relativedelta(months=3)
            )
            subscription.write(
                {
                    "kpi_1month_mrr_delta": delta_1month["delta"],
                    "kpi_1month_mrr_percentage": delta_1month["percentage"],
                    "kpi_3months_mrr_delta": delta_3months["delta"],
                    "kpi_3months_mrr_percentage": delta_3months["percentage"],
                }
            )

    def _get_portal_return_action(self):
        if self.is_subscription:
            return self.env.ref("sale_subscription.sale_subscription_action")
        else:
            return super()._get_portal_return_action()

    def _prepare_payment_link_vals(self):
        res = super()._prepare_payment_link_vals()
        if self.is_subscription and self.invoice_count and self.state == "done":
            next_billing_details = self._next_billing_details()
            amount_max = next_billing_details.get("next_invoice_amount") or 0.0
            res.update(
                {
                    "amount": amount_max,
                    "amount_max": amount_max,
                }
            )
        return res

    @api.model
    def _cron_recurring_create_invoice(self):
        deferred_account = (
            self.env.company.account_config_id.deferred_revenue_account_id
        )
        deferred_journal = (
            self.env.company.account_config_id.deferred_revenue_journal_id
        )
        if not deferred_account or not deferred_journal:
            raise ValidationError(
                self.env._(
                    "The deferred settings are not properly set. Please complete them to generate subscription deferred revenues"
                )
            )
        return self._create_recurring_invoice()

    def _split_invoiceable_line_ids(self, final) -> tuple:
        line_ids, down_payment_ids = super()._split_invoiceable_line_ids(final)
        discount_line_ids = self.line_ids.filtered(
            lambda line: (
                line.display_type == "subscription_discount" and line.state == "done"
            )
        ).ids
        return line_ids + discount_line_ids, down_payment_ids

    def _subscription_post_success_free_renewal(self) -> None:
        self.check_singleton()
        msg_body = self.env._(
            "Automatic renewal succeeded. Free subscription. Next Invoice: %(inv)s. No email sent.",
            inv=self.next_invoice_date,
        )
        self.message_post(body=msg_body)

    def _subscription_post_success_payment(
        self, transaction, invoices, automatic=True
    ) -> None:
        self.check_singleton()
        transaction.check_singleton()
        for invoice in invoices:
            invoice.write(
                {
                    "payment_reference": transaction.reference,
                    "ref": transaction.reference,
                }
            )
            if automatic:
                msg_body = self.env._(
                    "Automatic payment succeeded. Payment reference: %(ref)s. Amount: %(amount)s. Contract set to: In Progress, Next Invoice: %(inv)s. Email sent to customer.",
                    ref=transaction._get_html_link(title=transaction.reference),
                    amount=transaction.amount,
                    inv=self.next_invoice_date,
                )
            else:
                msg_body = self.env._(
                    "Manual payment succeeded. Payment reference: %(ref)s. Amount: %(amount)s. Contract set to: In Progress, Next Invoice: %(inv)s. Email sent to customer.",
                    ref=transaction._get_html_link(title=transaction.reference),
                    amount=transaction.amount,
                    inv=self.next_invoice_date,
                )
            self.message_post(body=msg_body)
            if invoice.state != "posted":
                with invoice._exempting_posting_from_approval("payment_received"):
                    invoice.with_context(ocr_trigger_delta=15)._post()
        MixinAccountMoveSend = self.env["mixin.account.move.send"]
        if moves_to_send := invoices.filtered(
            lambda move: (
                not move.is_move_sent
                and MixinAccountMoveSend._get_default_extra_edis(move)
            ),
        ):
            MixinAccountMoveSend._generate_and_send_invoices(moves=moves_to_send)

    def _get_subscription_mail_payment_context(self, mail_ctx=None) -> dict:
        self.check_singleton()
        if not mail_ctx:
            mail_ctx = {}
        billing_details = self._next_billing_details()
        return {
            **self.env.context,
            **mail_ctx,
            "next_invoice_amount": billing_details["next_invoice_amount"],
            "total_amount": self.amount_total,
            "currency_name": self.currency_id.name,
            "responsible_email": self.user_id.email,
            "code": self.client_order_ref,
        }

    def _update_next_invoice_date(self) -> None:
        for order in self:
            if not order.is_subscription:
                continue
            next_invoice_dates = []
            for line in order.line_ids:
                parameters = line._get_invoice_line_parameters()
                next_invoice_dates.append(parameters[1] + relativedelta(days=1))
            order.next_invoice_date = next_invoice_dates and min(next_invoice_dates)
            order.last_reminder_date = False

    def _update_subscription_payment_failure_values(self) -> dict:
        return {}

    def _post_invoice_hook(self) -> None:
        self.line_ids._reset_subscription_quantity_post_invoice()

    def _handle_post_invoice_hook_exception(self) -> None:
        return

    def _handle_subscription_payment_failure(self, invoice, transaction) -> None:
        current_date = fields.Date.today()
        reminder_mail_template = self.env.ref(
            "sale_subscription.email_payment_reminder", raise_if_not_found=False
        )
        close_mail_template = self.env.ref(
            "sale_subscription.email_payment_close", raise_if_not_found=False
        )
        invoice.unlink()
        self.pending_transaction = False
        for order in self:
            auto_close_days = self.plan_id.auto_close_limit or 15
            date_close = order.next_invoice_date + relativedelta(days=auto_close_days)
            close_contract = current_date >= date_close
            email_context = order._get_subscription_mail_payment_context()
            _logger.info(
                "Failed to create recurring invoice for contract %s",
                order.client_order_ref or order.name,
            )
            if close_contract:
                close_mail_template.with_context(email_context).send_mail(order.id)
                _logger.debug(
                    "Sending Contract Closure Mail to %s for contract %s and closing contract",
                    order.partner_id.email,
                    order.id,
                )
                msg_body = self.env._(
                    "Automatic payment failed after multiple attempts. Contract closed automatically."
                )
                order.message_post(body=msg_body)
                subscription_values = {"payment_exception": False}
                order.set_close(
                    close_reason_id=order.env.ref(
                        "sale_subscription.close_reason_auto_close_limit_reached"
                    ).id
                )
            else:
                msg_body = self.env._(
                    "Automatic payment failed. No email sent this time. Error: %s",
                    (transaction and transaction.state_message)
                    or self.env._("No valid Payment Method"),
                )
                if (fields.Date.today() - order.next_invoice_date).days in [2, 7, 14]:
                    email_context.update(
                        {
                            "date_close": date_close,
                            "payment_token": order.payment_token_id.display_name,
                            "payment_link": order.get_portal_url(),
                        }
                    )
                    reminder_mail_template.with_context(email_context).send_mail(
                        order.id
                    )
                    _logger.debug(
                        "Sending Payment Failure Mail to %s for contract %s and setting contract to pending",
                        order.partner_id.email,
                        order.id,
                    )
                    msg_body = self.env._(
                        "Automatic payment failed. Email sent to customer. Error: %s",
                        (transaction and transaction.state_message)
                        or self.env._("No Payment Method"),
                    )
                order.message_post(body=msg_body)
                subscription_values = {"payment_exception": False, "is_batch": True}
            subscription_values.update(
                order._update_subscription_payment_failure_values()
            )
            order.write(subscription_values)

    def _get_domain_rollup_pending_lines(self, state_field) -> Domain:
        domain = super()._get_domain_rollup_pending_lines(state_field)
        if state_field != "invoice_state":
            return domain
        return domain & ~Domain(
            [
                ("order_id.subscription_state", "in", SUBSCRIPTION_CLOSED_STATE),
                ("recurring_invoice", "=", True),
                ("product_id.invoice_policy", "!=", "transferred"),
            ]
        )

    def _invoice_is_considered_free(self, invoiceable_lines) -> tuple:
        currency = self.currency_id[:1]
        amount_total = sum(invoiceable_lines.mapped("price_total"))
        non_recurring_line = invoiceable_lines.filtered(
            lambda l: not l.recurring_invoice
        )
        delivery_invoiceable_lines = invoiceable_lines.filtered(
            lambda l: l._is_postpaid_line() and l.qty_transferred
        )
        is_free, is_exception = False, False
        mrr = sum(self.mapped("recurring_monthly"))
        total_sign = currency.compare_amounts(amount_total, 0)
        if (
            currency.compare_amounts(mrr, 0) < 0 or total_sign < 0
        ) and non_recurring_line:
            is_free = True
            is_exception = True
        elif (
            (total_sign < 0 and not delivery_invoiceable_lines)
            or (
                total_sign == 0
                and not non_recurring_line
                and not delivery_invoiceable_lines
            )
            or (
                currency.compare_amounts(mrr, 0) < 1
                and not non_recurring_line
                and not delivery_invoiceable_lines
            )
        ):
            is_free = True
        return is_free, is_exception

    def _invoice_requires_payment(self, invoiceable_lines) -> bool:
        if self._invoice_is_considered_free(invoiceable_lines)[0]:
            return False
        currency = self.currency_id[:1]
        amount_total = sum(invoiceable_lines.mapped("price_total"))
        return currency.compare_amounts(amount_total, 0) > 0

    def _recurring_invoice_domain(self, extra_domain=None):
        if not extra_domain:
            extra_domain = []
        current_date = fields.Date.today()
        search_domain = [
            ("is_batch", "=", False),
            ("is_subscription", "=", True),
            ("subscription_state", "=", "3_progress"),
            ("payment_exception", "=", False),
            ("pending_transaction", "=", False),
            ("company_id.active", "=", True),
            "|",
            ("next_invoice_date", "<=", current_date),
            ("end_date", "<=", current_date),
        ]
        if extra_domain:
            search_domain = Domain.AND([search_domain, extra_domain])
        return search_domain

    def _get_invoice_grouping_keys(self):
        if any(self.mapped("is_subscription")):
            return super()._get_invoice_grouping_keys() + [
                "payment_token_id",
                "partner_invoice_id",
            ]
        else:
            return super()._get_invoice_grouping_keys()

    def _get_auto_invoice_grouping_keys(self):
        grouping_keys = super()._get_invoice_grouping_keys() + [
            "payment_token_id",
            "partner_invoice_id",
        ]
        grouping_keys = list(set(grouping_keys))
        grouping_keys.remove("partner_id")
        return grouping_keys

    def _get_invoiced_subscriptions(self):
        return set(
            self.env["account.move.line"]
            .search(
                [
                    ("subscription_id", "in", self.ids),
                    ("move_type", "=", "out_invoice"),
                    ("move_id.state", "in", ["draft", "posted"]),
                ]
            )
            .subscription_id.ids
        )

    def _get_subscriptions_to_invoice(self, limit=False) -> Self:
        invoiced_sub_ids = self._get_invoiced_subscriptions()
        to_invoice_ids = []
        for sub in self:
            if (
                sub.payment_token_id
                or not sub.require_payment
                or (sub.id not in invoiced_sub_ids and sub.prepayment_percent != 1)
                or not sub._invoice_requires_payment(
                    sub.with_context(recurring_automatic=True)._get_invoiceable_lines()
                )
            ):
                to_invoice_ids.append(sub.id)
            if limit and len(to_invoice_ids) >= limit:
                break
        return self.browse(to_invoice_ids)

    def _recurring_invoice_get_subscriptions(
        self, grouped=False, batch_size=30
    ) -> tuple:
        need_cron_trigger = False
        limit = False
        if self:
            domain = [
                ("id", "in", self.ids),
                ("subscription_state", "in", SUBSCRIPTION_PROGRESS_STATE),
                ("company_id.active", "=", True),
            ]
            batch_size = False
        else:
            domain = self._recurring_invoice_domain()
            limit = batch_size and batch_size + 1

        if grouped:
            all_subscriptions = self._read_group(
                domain,
                self._get_auto_invoice_grouping_keys(),
                ["id:recordset"],
                limit=limit or None,
            )
            need_cron_trigger = batch_size and len(all_subscriptions) > batch_size
            all_subscriptions = [
                subscriptions._get_subscriptions_to_invoice()
                for *__, subscriptions in all_subscriptions
            ]
        else:
            all_subscriptions = self.search(domain)._get_subscriptions_to_invoice(limit)
            need_cron_trigger = batch_size and len(all_subscriptions) > batch_size

        if batch_size:
            all_subscriptions = all_subscriptions[:batch_size]

        return all_subscriptions, need_cron_trigger

    def _subscription_commit_cursor(self, auto_commit, remaining=None) -> None:
        if auto_commit:
            self.env["ir.cron"]._commit_progress(processed=1, remaining=remaining)
        else:
            self.env.flush_all()
            self.env.cr.flush()

    def _subscription_rollback_cursor(self, auto_commit) -> None:
        if auto_commit:
            self.env.cr.rollback()

    def _subscription_launch_cron_parallel(self, batch_size) -> None:
        self.env["ir.cron"]._trigger_ref(
            "sale_subscription.account_analytic_cron_for_invoice"
        )

    def _get_subscription_payment_exception_condition(self) -> bool:
        return False

    def _create_recurring_invoice(self, batch_size=30):
        today = fields.Date.today()
        auto_commit = not (
            modules.module.current_test or self.env.context.get("install_mode")
        )
        grouped_invoice = self.env["ir.config_parameter"].get_param_bool(
            "sale_subscription.invoice_consolidation"
        )
        all_subscriptions, need_cron_trigger = (
            self._recurring_invoice_get_subscriptions(
                grouped=grouped_invoice, batch_size=batch_size
            )
        )
        _debug.pipeline(
            "recurring_invoice_batch",
            subscriptions=len(all_subscriptions),
            grouped=grouped_invoice,
        )
        if not all_subscriptions:
            return self.env["account.move"]

        all_invoiceable_lines = self.env["sale.order.line"]
        order_to_remove_ids = []
        for subscription in all_subscriptions:
            subscription = subscription.with_context(mail_auto_subscribe_no_notify=True)
            auto_close_subscription = subscription.filtered_domain(
                [("end_date", "!=", False)]
            )
            closed_contract = auto_close_subscription._subscription_auto_close()
            subscription -= closed_contract
            order_to_remove_ids += closed_contract.ids
            all_invoiceable_lines += subscription.with_context(
                recurring_automatic=True
            )._get_invoiceable_lines()

        if not isinstance(all_subscriptions, list):
            all_subscriptions -= self.env["sale.order"].browse(order_to_remove_ids)
        lines_to_reset_qty = self.env["sale.order.line"]
        account_moves = self.env["account.move"]
        all_invoiceable_lines._reset_subscription_qty_to_invoice()
        if auto_commit:
            self.env["ir.cron"]._commit_progress(remaining=len(all_subscriptions))
        self._subscription_commit_cursor(auto_commit)
        for done, subscription in enumerate(all_subscriptions, start=1):
            if auto_commit:
                subscription = subscription.with_prefetch()
            subscription.is_invoice_cron = True
            subscription = subscription.filtered(
                lambda sub: (
                    sub.subscription_state == "3_progress" and not sub.payment_exception
                )
            )
            if not subscription:
                _debug.logic("subscription_skipped", reason="not_progress")
                continue
            try:
                self._subscription_commit_cursor(auto_commit)
                draft_invoices = subscription.invoice_ids.filtered(
                    lambda am: am.state == "draft"
                )
                if subscription.payment_token_id and draft_invoices:
                    _debug.lifecycle(
                        "draft_invoices_cancelled", invoices=draft_invoices
                    )
                    draft_invoices.action_cancel()
                elif draft_invoices:
                    _debug.logic(
                        "subscription_skipped", reason="draft_invoice_no_token"
                    )
                    continue
                invoiceable_lines = all_invoiceable_lines.filtered_domain(
                    [("order_id", "in", subscription.ids)]
                )
                invoice_is_free, is_exception = (
                    subscription._invoice_is_considered_free(invoiceable_lines)
                )
                if not invoiceable_lines or invoice_is_free:
                    updatable_invoice_date = subscription.filtered(
                        lambda sub: (
                            sub.next_invoice_date and sub.next_invoice_date <= today
                        )
                    )
                    _debug.logic(
                        "subscription_not_invoiced",
                        free=invoice_is_free,
                        exception=is_exception,
                        lines=invoiceable_lines,
                    )
                    if is_exception:
                        for sub in subscription:
                            msg_body = self.env._(
                                "Mix of negative recurring lines and non-recurring line. The contract should be fixed manually",
                            )
                            sub.message_post(body=msg_body)
                        subscription.payment_exception = True
                    elif updatable_invoice_date:
                        updatable_invoice_date.with_context(
                            force_postpaid_next_invoice=True
                        )._update_next_invoice_date()
                        if invoice_is_free:
                            updatable_invoice_date._subscription_post_success_free_renewal()
                            subscription.is_invoice_cron = False
                    continue

                try:
                    invoice = subscription.with_context(
                        recurring_automatic=True
                    )._create_invoices(final=True)
                    _debug.lifecycle("recurring_invoice_created", invoice=invoice)
                    lines_to_reset_qty |= invoiceable_lines
                except Exception as e:
                    if not auto_commit and isinstance(e, TransactionRollbackError):
                        raise
                    self._subscription_rollback_cursor(auto_commit)
                    for sub in subscription:
                        email_context = sub._get_subscription_mail_payment_context()
                        error_message = self.env._(
                            "Error during renewal of contract %s (Payment not recorded)",
                            sub.name,
                        )
                        _debug.logic("recurring_invoice_failed", subscription=sub)
                        _logger.exception(error_message)
                        body = self._get_traceback_body(e, error_message)
                        mail = (
                            self.env["mail.mail"]
                            .sudo()
                            .create(
                                {
                                    "body_html": body,
                                    "subject": error_message,
                                    "email_to": email_context["responsible_email"],
                                    "auto_delete": True,
                                }
                            )
                        )
                        mail.send()
                    continue
                self._subscription_commit_cursor(auto_commit)
                existing_invoices = (
                    subscription.with_context(
                        recurring_automatic=True
                    )._handle_automatic_invoices(invoice, auto_commit)
                    or self.env["account.move"]
                )
                account_moves |= existing_invoices
                if subscription._get_subscription_payment_exception_condition() or all(
                    inv.state != "draft" for inv in existing_invoices
                ):
                    subscription.with_context(
                        mail_notrack=True
                    ).payment_exception = False
                if not subscription.payment_token_id:
                    self._process_invoices_to_send(existing_invoices)

                self._subscription_commit_cursor(auto_commit)
                try:
                    subscription._post_invoice_hook()
                    self._subscription_commit_cursor(auto_commit)
                except Exception:
                    self._subscription_rollback_cursor(auto_commit)
                    _debug.logic("post_invoice_hook_failed", subscription=subscription)
                    _logger.exception("Error during post invoice action")
                    subscription._handle_post_invoice_hook_exception()
                subscription.is_invoice_cron = False
                self._subscription_commit_cursor(
                    auto_commit, remaining=len(all_subscriptions) - done
                )
            except Exception:
                name_list = [
                    f"{sub.name} {sub.client_order_ref}" for sub in subscription
                ]
                _logger.exception(
                    "Error during renewal of contract %s", "; ".join(name_list)
                )
                self._subscription_rollback_cursor(auto_commit)
        self._subscription_commit_cursor(auto_commit, remaining=0)
        if need_cron_trigger:
            _debug.pipeline("recurring_invoice_cron_relaunched", batch_size=batch_size)
            self._subscription_launch_cron_parallel(batch_size)
        else:
            subscriptions_to_reset = self.search(
                ["|", ("is_batch", "=", True), ("is_invoice_cron", "=", True)]
            )
            _debug.lifecycle(
                "recurring_invoice_flags_cleared", subscriptions=subscriptions_to_reset
            )
            subscriptions_to_reset.write(
                {"is_invoice_cron": False, "is_batch": False, "user_pause_start": False}
            )
            self._subscription_commit_cursor(auto_commit)
        return account_moves

    def _create_invoices(self, grouped=False, final=False, date=None):
        order_already_invoiced = self.env["sale.order"]
        for order in self:
            if (
                order.is_subscription
                and order.line_ids.invoice_line_ids.move_id.filtered(
                    lambda r: (
                        r.move_type in ("out_invoice", "out_refund")
                        and r.state == "draft"
                    )
                )
            ):
                order_already_invoiced |= order
        if order_already_invoiced:
            order_error = ", ".join(order_already_invoiced.mapped("name"))
            _debug.logic(
                "invoice_refused",
                orders=order_already_invoiced,
                reason="draft_invoice_exists",
            )
            raise ValidationError(
                self.env._(
                    "The following recurring orders have draft invoices. Please Confirm them or cancel them "
                    "before creating new invoices. %s.",
                    order_error,
                )
            )
        return super()._create_invoices(grouped=grouped, final=final, date=date)

    def _subscription_auto_close(self):
        current_date = fields.Date.context_today(self)
        close_contract_ids = self.filtered(
            lambda contract: contract.end_date and contract.end_date <= current_date
        )
        _debug.lifecycle(
            "subscription_auto_closed",
            candidates=self,
            closed=close_contract_ids,
            on=current_date,
        )
        close_contract_ids.set_close()
        return close_contract_ids

    def _is_invoice_post_required(self) -> bool:
        return not self.payment_token_id or len(self.payment_token_id) > 1

    def _process_auto_invoice(self, invoice) -> None:
        invoice.action_post()

    def _handle_automatic_invoices(self, invoice, auto_commit):
        Mail = self.env["mail.mail"]
        self.with_context(mail_notrack=True).write({"payment_exception": True})
        payment_token = self.payment_token_id
        if self._is_invoice_post_required() or invoice.currency_id.is_zero(
            invoice.amount_total
        ):
            _debug.logic("automatic_invoice", by="post_without_payment")
            self._process_auto_invoice(invoice)
            return invoice

        if not payment_token.partner_id.country_id:
            msg_body = self.env._(
                "Automatic payment failed. No country specified on payment_token's partner"
            )
            for order in self:
                order.message_post(body=msg_body)
            _debug.logic("automatic_payment_refused", reason="token_no_country")
            invoice.unlink()
            self._subscription_commit_cursor(auto_commit)
            return None

        existing_transactions = self.transaction_ids
        try:
            self.pending_transaction = True
            if invoice.currency_id.compare_amounts(invoice.amount_total_signed, 0) < 0:
                self.pending_transaction = False
                msg_body = self.env._(
                    "Automatic payment failed. Check the corresponding invoice %s. We can't automatically process negative payment",
                    invoice._get_html_link(),
                )
                for order in self:
                    order.message_post(body=msg_body)
                self._subscription_commit_cursor(auto_commit)
                return invoice
            transaction = self._do_payment(
                payment_token, invoice, auto_commit=auto_commit
            )

            if not transaction or transaction.renewal_state == "cancel":
                self._handle_subscription_payment_failure(invoice, transaction)
                self._subscription_commit_cursor(auto_commit)
                return None
            elif transaction.renewal_state == "pending":
                self.payment_exception = False
                self._subscription_commit_cursor(auto_commit)
            elif transaction.renewal_state == "authorized":
                self.payment_exception = False
                self._subscription_commit_cursor(auto_commit)
                with invoice._exempting_posting_from_approval("payment_received"):
                    invoice._post()
                self._subscription_commit_cursor(auto_commit)

        except Exception as e:
            last_tx_sudo = (self.transaction_ids - existing_transactions).sudo()
            if last_tx_sudo and last_tx_sudo.renewal_state in ["pending", "done"]:
                payment_state = self.env._(
                    "Payment recorded: %s", last_tx_sudo.reference
                )
            else:
                payment_state = self.env._("Payment not recorded")
            error_message = self.env._(
                "Error during renewal of contract %(order_ids)s %(order_refs)s %(payment_state)s",
                order_ids=str(self.ids),
                order_refs=self.mapped(
                    lambda order: order.client_order_ref or order.name
                ),
                payment_state=payment_state,
            )
            _debug.logic("automatic_payment_failed", error=type(e).__name__)
            body = self._get_traceback_body(e, error_message)
            _logger.exception(error_message)
            self._subscription_rollback_cursor(auto_commit)
            mail = Mail.sudo().create(
                [
                    {
                        "body_html": body,
                        "subject": error_message,
                        "email_to": order._get_subscription_mail_payment_context().get(
                            "responsible_email"
                        ),
                        "auto_delete": True,
                    }
                    for order in self
                ]
            )
            mail.send()
            if invoice.state == "draft":
                if not last_tx_sudo.exists() or last_tx_sudo.renewal_state in [
                    "draft",
                    "cancel",
                ]:
                    _debug.lifecycle("failed_invoice_removed", invoice=invoice)
                    invoice.unlink()
                    return None
        return invoice

    def _get_traceback_body(self, exc, body):
        if not str2bool(
            self.env.registry.settings.get(
                self.env, "sale_subscription.full_mail_traceback", False
            )
        ):
            return plaintext2html("%s\n\n%s" % (body, str(exc)))
        return plaintext2html(
            "%s\n\n%s\n%s"
            % (body, "".join(traceback.format_tb(exc.__traceback__)), str(exc)),
        )

    def _get_expired_subscriptions(self):
        today = fields.Datetime.today()
        self.env.cr.execute(
            """
                SELECT (so.next_invoice_date + INTERVAL '1 day' * COALESCE(ssp.auto_close_limit,15)) AS "payment_limit",
                           so.next_invoice_date,
                           so.id AS so_id
                  FROM sale_order so
             LEFT JOIN sale_subscription_plan ssp ON ssp.id=so.plan_id
                 WHERE so.is_subscription
                   AND so.state = 'done'
                   AND so.subscription_state = '3_progress'
                AND (so.next_invoice_date + INTERVAL '1 day' * COALESCE(ssp.auto_close_limit,15))< %s
            """,
            [today.strftime("%Y-%m-%d")],
        )
        return self.env.cr.dictfetchall()

    def _get_unpaid_subscriptions(self):
        today = fields.Datetime.today()
        self.env.cr.execute(
            """
                WITH payment_limit_query AS (
                      SELECT (aml2.dm + INTERVAL '1 day' * COALESCE(ssp.auto_close_limit,15) ) AS "payment_limit",
                              aml2.dm AS date_maturity,
                              ssp.repeat_unit AS unit,
                              ssp.repeat_interval AS duration,
                              CASE
                                WHEN ssp.repeat_unit='week' THEN INTERVAL '1 day' * 7 * ssp.repeat_interval
                                WHEN ssp.repeat_unit='month' THEN INTERVAL '1 day' * 30 * ssp.repeat_interval
                                WHEN ssp.repeat_unit='year' THEN INTERVAL '1 day' * 365 * ssp.repeat_interval
                              END AS conversion,
                              ssp.repeat_interval || ' ' || ssp.repeat_unit AS recurrence,
                              am.payment_state AS payment_state,
                              am.id AS am_id,
                              so.id AS so_id,
                              so.next_invoice_date AS next_invoice_date
                        FROM sale_order so
                        JOIN sale_order_line sol ON sol.order_id = so.id
                        JOIN account_move_line aml ON aml.subscription_id = so.id
                        JOIN account_move am ON am.id = aml.move_id
                        JOIN sale_subscription_plan ssp ON ssp.id=so.plan_id
                        JOIN account_move_line_sale_order_line_rel rel ON rel.move_line_id=aml.id
           LEFT JOIN LATERAL ( SELECT MAX(date_maturity) AS dm FROM account_move_line aml WHERE aml.move_id = am.id) AS aml2 ON TRUE
                      WHERE so.is_subscription
                        AND so.state = 'done'
                        AND so.subscription_state ='3_progress'
                        AND am.payment_state = 'not_paid'
                        AND am.move_type = 'out_invoice'
                        AND am.state = 'posted'
                        AND rel.order_line_id=sol.id
                   GROUP BY so_id, am_id, ssp.auto_close_limit, payment_state, aml2.dm, ssp.repeat_unit, ssp.repeat_interval
               )
              SELECT payment_limit::DATE,
                     date_maturity,
                     recurrence,
                     next_invoice_date - plq.conversion AS last_invoice_date,
                     payment_state,
                     am_id,
                     so_id,
                     next_invoice_date
                FROM
                    payment_limit_query plq
                    WHERE payment_limit < %s and payment_limit >= (next_invoice_date - plq.conversion)::DATE
            """,
            [today.strftime("%Y-%m-%d")],
        )
        return self.env.cr.dictfetchall()

    def _handle_unpaid_subscriptions(self) -> dict:
        unpaid_result = self._get_unpaid_subscriptions()
        return {res["so_id"]: res["am_id"] for res in unpaid_result}

    def _cron_subscription_expiration(self) -> dict:
        self.env["sale.order"].flush_model(
            fnames=[
                "line_ids",
                "plan_id",
                "state",
                "subscription_state",
                "next_invoice_date",
            ]
        )
        self.env["account.move"].flush_model(fnames=["payment_state", "line_ids"])
        self.env["account.move.line"].flush_model(fnames=["move_id", "sale_line_ids"])
        self.env["sale.subscription.plan"].flush_model(fnames=["auto_close_limit"])
        today = fields.Date.today()
        domain_close = [
            ("is_subscription", "=", True),
            ("end_date", "<", today),
            ("state", "=", "done"),
            ("subscription_state", "in", SUBSCRIPTION_PROGRESS_STATE),
        ]
        subscriptions_close = self.search(domain_close)
        unpaid_results = self._handle_unpaid_subscriptions()
        unpaid_ids = unpaid_results.keys()
        expired_result = self._get_expired_subscriptions()
        expired_ids = [r["so_id"] for r in expired_result]
        subscriptions_close |= self.env["sale.order"].browse(unpaid_ids) | self.env[
            "sale.order"
        ].browse(expired_ids)
        auto_commit = can_commit()
        expired_close_reason = self.env.ref(
            "sale_subscription.close_reason_auto_close_limit_reached"
        )
        unpaid_close_reason = self.env.ref(
            "sale_subscription.close_reason_unpaid_subscription"
        )
        for batched_to_close in (
            self.env["sale.order"].browse(b)
            for b in batched(subscriptions_close.ids, 30, strict=False)
        ):
            unpaid_so = self.env["sale.order"]
            expired_so = self.env["sale.order"]
            for so in batched_to_close:
                if so.id in unpaid_ids:
                    unpaid_so |= so
                    account_move = self.env["account.move"].browse(
                        unpaid_results[so.id]
                    )
                    so.message_post(
                        body=self.env._(
                            "The last invoice (%s) of this subscription is unpaid after the due date.",
                            account_move._get_html_link(),
                        ),
                        partner_ids=so.team_user_id.partner_id.ids,
                    )
                elif so.id in expired_ids:
                    expired_so |= so

            unpaid_so.set_close(close_reason_id=unpaid_close_reason.id)
            expired_so.set_close(close_reason_id=expired_close_reason.id)
            (batched_to_close - unpaid_so - expired_so).set_close()
            if auto_commit:
                self.env["ir.cron"]._commit_progress(processed=len(batched_to_close))
        return {"closed": subscriptions_close.ids}

    def _get_subscription_delta(self, date) -> dict:
        self.check_singleton()
        delta, percentage = False, False
        subscription_log = self.env["sale.order.log"].search(
            [
                ("order_id", "=", self.id),
                (
                    "event_type",
                    "in",
                    ["0_creation", "1_expansion", "15_contraction", "2_transfer"],
                ),
                ("event_date", "<=", date),
            ],
            order="event_date desc",
            limit=1,
        )
        if subscription_log:
            delta = self.recurring_monthly - subscription_log.recurring_monthly
            percentage = (
                delta / subscription_log.recurring_monthly
                if subscription_log.recurring_monthly != 0
                else 100
            )
        return {"delta": delta, "percentage": percentage}

    def _get_nothing_to_invoice_error_message(self):
        error_message = super()._get_nothing_to_invoice_error_message()
        if any(self.mapped("is_subscription")):
            error_message += self.env._(
                "\n- You are trying to invoice recurring orders. "
                "Please verify the delivered quantity of product based on invoicing policy, "
                "next invoice date and end date of the contract."
            )
        return error_message

    def _do_payment(self, payment_token, invoice, auto_commit=False):
        values = [
            {
                "provider_id": payment_token.provider_id.id,
                "payment_method_id": payment_token.payment_method_id.id,
                "sale_order_ids": self.ids,
                "amount": invoice.amount_total,
                "currency_id": invoice.currency_id.id,
                "partner_id": invoice.partner_id.id,
                "token_id": payment_token.id,
                "operation": "offline",
                "invoice_ids": [Command.set([invoice.id])],
                "subscription_action": "automatic_send_mail",
            }
        ]
        transactions_sudo = self.env["payment.transaction"].sudo().create(values)
        _debug.lifecycle(
            "offline_transaction_created",
            subscriptions=self,
            transaction=transactions_sudo,
            invoice=invoice,
        )
        self._subscription_commit_cursor(auto_commit)
        for tx_sudo in transactions_sudo:
            tx_sudo.lock_for_update(wait=True, allow_referencing=True)
            tx_sudo._charge_with_token()
        return transactions_sudo

    @api.model
    def _process_invoices_to_send(self, account_moves) -> None:
        for invoice in account_moves:
            if (
                not invoice.is_move_sent
                and invoice._is_ready_to_be_sent()
                and invoice.state == "posted"
            ):
                subscription = invoice.line_ids.subscription_id
                subscription.post_and_send_invoice(invoice)
                invoice.message_subscribe(subscription.user_id.partner_id.ids)
            elif invoice.line_ids.subscription_id:
                invoice.message_subscribe(
                    invoice.line_ids.subscription_id.user_id.partner_id.ids
                )

    def post_and_send_invoice(self, invoice) -> None:
        email_context = {
            **self.env.context.copy(),
            "total_amount": invoice.amount_total,
            "email_to": invoice.partner_id.email,
            "code": ", ".join(
                subscription.client_order_ref or subscription.name
                for subscription in self
            ),
            "currency": invoice.currency_id.name,
        }
        auto_commit = can_commit()
        self._subscription_commit_cursor(auto_commit)
        if self.plan_id.invoice_mail_template_id:
            _logger.debug(
                "Sending Invoice Mail to %s for subscription %s",
                self.partner_id.mapped("email"),
                self.ids,
            )
            invoice.with_context(email_context)._generate_and_send_automatically(
                mail_template=self.plan_id.invoice_mail_template_id
            )

    def _update_token(self, tx) -> bool:
        if tx.renewal_state == "authorized":
            self.payment_token_id = tx.token_id.id
            return True
        return False

    def _get_name_portal_content_view(self):
        return (
            "sale_subscription.subscription_portal_content"
            if self.is_subscription
            else super()._get_name_portal_content_view()
        )

    def _get_upsell_portal_url(self):
        self.check_singleton()
        upsell = self.subscription_child_ids.filtered(
            lambda so: (
                so.subscription_state == "7_upsell" and so.state == "draft" and so.sent
            )
        )[:1]
        return upsell.get_portal_url() if upsell else False

    def _get_renewal_portal_url(self):
        self.check_singleton()
        renewal = self.subscription_child_ids.filtered(
            lambda so: (
                so.subscription_state == "2_renewal" and so.state == "draft" and so.sent
            )
        )[:1]
        return renewal.get_portal_url() if renewal else False

    def _can_be_edited_on_portal(self) -> bool:
        self.check_singleton()
        if self.is_subscription:
            return (
                (
                    not self.next_invoice_date
                    or self.next_invoice_date == self.start_date
                )
                and self.subscription_state
                in SUBSCRIPTION_DRAFT_STATE + SUBSCRIPTION_PROGRESS_STATE
            )
        else:
            return super()._can_be_edited_on_portal()

    def _portal_plan_choices(self):
        self.check_singleton()
        if not self.is_subscription or not self._can_be_edited_on_portal():
            return self.env["sale.subscription.plan"]
        if not self.plan_id.related_plan_id:
            return self.env["sale.subscription.plan"]
        return self.plan_id | self.plan_id.related_plan_id

    def _next_billing_details(self) -> dict:
        self.check_singleton()
        AccountTax = self.env["account.tax"]

        def get_tax_totals(display_lines):
            base_lines = [
                line._prepare_base_line_for_taxes_computation()
                for line in display_lines
            ]
            AccountTax._add_tax_details_in_base_lines(base_lines, self.company_id)
            AccountTax._round_base_lines_tax_details(base_lines, self.company_id)
            return AccountTax._get_tax_totals_summary(
                base_lines=base_lines,
                currency=self.currency_id or self.company_id.currency_id,
                company=self.company_id,
            )

        display_lines = self._get_invoiceable_lines()
        amount_to_pay = get_tax_totals(display_lines) if display_lines else {}

        undelivered_lines = self.line_ids.filtered(
            lambda line: (
                line.product_qty
                and not line.qty_transferred
                and line.product_id.invoice_policy == "transferred"
            )
        )
        if undelivered_lines:
            display_lines += undelivered_lines
        if not display_lines:
            display_lines = self.line_ids.filtered(
                lambda line: line.product_id.recurring_invoice
            )
        if self.subscription_state == "5_renewed":
            display_lines = self.line_ids

        tax_totals = get_tax_totals(display_lines)
        return {
            "sale_order": self,
            "display_lines": display_lines,
            "next_invoice_amount": amount_to_pay.get("total_amount_currency") or 0.0,
            "tax_totals": tax_totals,
        }

    def _upsell_activity_line(self):
        self.check_singleton()
        return Markup("&nbsp;<br>").join(
            escape(
                self.env._(
                    "- You delivered %(delivered)s %(name)s and invoiced %(invoiced)s",
                    delivered=line.qty_transferred,
                    name=line.name,
                    invoiced=line.qty_invoiced,
                )
            )
            for line in self.line_ids
            if line._is_upsell_opportunity()
        )

    def _create_upsell_activity(self) -> None:
        subscription = self.filtered("is_subscription")
        super(SaleOrder, self - subscription)._create_upsell_activity()

        for sub in subscription:
            order_ref = sub._get_html_link()
            customer_ref = sub.partner_id._get_html_link()
            lines = sub._upsell_activity_line()
            sub.activity_schedule(
                "mail.mail_activity_data_todo",
                user_id=sub.user_id.id or sub.partner_id.user_id.id,
                note=self.env._(
                    "Upsell %(order)s for customer %(customer)s for the period %(date_start)s to %(date_end)s %(nl)s%(lines)s",
                    order=order_ref,
                    customer=customer_ref,
                    lines=lines,
                    date_start=sub.last_invoice_date,
                    date_end=sub.next_invoice_date,
                    nl=Markup("&nbsp;<br>"),
                ),
            )

    def _subscription_reminder_parameters(self) -> dict | None:
        current_date = fields.Date.today()
        reminder_days = [0, 2, 7, 14, -2, -7, -14]
        reminder_cron = self.env.ref(
            "sale_subscription.send_payment_reminder", raise_if_not_found=False
        )
        if not reminder_cron:
            return None
        last_call = reminder_cron.lastcall
        next_invoice_dates = [
            current_date + relativedelta(days=x) for x in reminder_days
        ]
        cron_call_shift = last_call and (current_date - last_call.date()).days
        if (
            cron_call_shift
            and cron_call_shift > 1
            and not self.env.context.get("subscription_no_lost_reminder")
        ):
            check_date = last_call.date() + relativedelta(days=1)
            while check_date < current_date:
                next_invice_date_with_delay = [
                    check_date + relativedelta(days=x) for x in reminder_days
                ]
                check_date += relativedelta(days=1)
                next_invoice_dates += next_invice_date_with_delay
        search_domain = [
            ("is_subscription", "=", True),
            ("subscription_state", "=", "3_progress"),
            ("pending_transaction", "=", False),
            ("payment_token_id", "=", False),
            ("require_payment", "=", True),
            ("last_reminder_date", "!=", current_date),
            "|",
            ("next_invoice_date", "in", list(set(next_invoice_dates))),
            ("next_invoice_date", "<=", current_date),
        ]
        return {"domain": search_domain, "next_invoice_dates": set(next_invoice_dates)}

    def _cron_recurring_send_payment_reminder(self) -> None:
        today = fields.Date.today()
        parameters = self._subscription_reminder_parameters()
        if not parameters:
            return
        all_subscriptions = self.search(parameters["domain"])
        invoiced_sub_ids = all_subscriptions._get_invoiced_subscriptions()
        for subscription in all_subscriptions:
            if (
                subscription.prepayment_percent != 1
                and subscription.id not in invoiced_sub_ids
            ):
                continue
            auto_close_days = subscription.plan_id.auto_close_limit or 15
            date_close = subscription.next_invoice_date + relativedelta(
                days=auto_close_days
            )
            close_contract = today >= date_close
            email_context = subscription._get_subscription_mail_payment_context()
            if (
                close_contract
                and subscription.next_invoice_date
                not in parameters["next_invoice_dates"]
            ):
                close_mail_template = self.env.ref(
                    "sale_subscription.email_payment_close", raise_if_not_found=False
                )
                if close_mail_template:
                    close_mail_template.with_context(email_context).send_mail(
                        subscription.id
                    )
                subscription.set_close(
                    close_reason_id=self.env.ref(
                        "sale_subscription.close_reason_auto_close_limit_reached"
                    ).id
                )
            elif (
                not subscription.last_reminder_date
                or subscription.last_reminder_date != today
            ) and subscription.next_invoice_date in parameters["next_invoice_dates"]:
                reminder_mail_template = self.env.ref(
                    "sale_subscription.email_payment_reminder", raise_if_not_found=False
                )
                email_context.update(
                    {
                        "date_close": date_close,
                        "payment_link": subscription.get_portal_url(),
                    }
                )
                if reminder_mail_template:
                    reminder_mail_template.with_context(email_context).send_mail(
                        subscription.id
                    )
                    subscription.last_reminder_date = today
            if (
                subscription.user_pause_start
                and subscription.next_invoice_date <= today
            ):
                subscription.user_pause_start = False

    def _get_ratio_value(self, new_upsell=False):
        self.check_singleton()
        today = fields.Date.today()
        if new_upsell:
            parent_id = self
            start_date = today
        else:
            parent_id = self.subscription_id
            start_date = max(
                self.start_date or today, self.first_contract_date or today
            )
        end_date = (parent_id and parent_id.next_invoice_date) or today
        if not end_date or start_date >= end_date:
            ratio = 0
        else:
            recurrence = parent_id.plan_id.billing_period
            complete_rec = 0
            while end_date - recurrence >= start_date:
                complete_rec += 1
                end_date -= recurrence
            ratio = (end_date - start_date).days / (
                (start_date + recurrence) - start_date
            ).days + complete_rec
        return ratio

    def _get_subscription_invoices(self):
        self.check_singleton()
        move = self.env["account.move"]
        if self.subscription_state == "7_upsell":
            move = self.line_ids.invoice_line_ids.move_id
        elif self.subscription_state:
            subscription_move_lines = self.env["account.move.line"].search(
                [("subscription_id", "in", self.ids)]
            )
            move = subscription_move_lines.move_id
        return move

    def _subscribe_followers_to_new_order(self, order) -> None:
        for follower in self.message_follower_ids:
            if follower.partner_id not in order.message_follower_ids.partner_id:
                order.message_subscribe(
                    partner_ids=follower.partner_id.ids,
                    subtype_ids=follower.subtype_ids.ids,
                )

    def _subscription_is_one_time_sale(self):
        return all(
            line._subscription_is_one_time_sale()
            for line in self.line_ids
            if line.recurring_invoice
        )

    def _is_subscription_postpaid(self) -> bool:
        self.check_singleton()
        return any(sol._is_postpaid_line() for sol in self.line_ids)

    def _post_subscription_activity(
        self, record=None, summary="", explanation=""
    ) -> None:
        for so in self:
            records_link = ", ".join([r._get_html_link() for r in record])
            note = self.env._(
                "%(explanation)s, but the billing period has already been invoiced. %(record)s",
                explanation=explanation,
                record=records_link,
            )
            so.activity_schedule(
                "mail.mail_activity_data_todo",
                summary=summary,
                note=note,
                user_id=so.user_id.id,
            )

    def _get_product_catalog_order_line_info(
        self, product_ids, child_field=False, **kwargs
    ):
        if self.plan_id:
            kwargs["plan_id"] = self.plan_id.id

        res = super()._get_product_catalog_order_line_info(
            product_ids, child_field=child_field, **kwargs
        )
        if not self.plan_id:
            return res

        for product in self.env["product.product"].browse(product_ids):
            if not product.recurring_invoice or not res.get(product.id):
                continue
            res[product.id]["plan_name"] = self.plan_id.name

        return res

    def _update_order_line_info(self, product_id, quantity, **kwargs):
        if self.plan_id:
            kwargs["plan_id"] = self.plan_id.id

        return super()._update_order_line_info(product_id, quantity, **kwargs)

    def _is_paid(self) -> bool:
        self.check_singleton()
        if not self.is_subscription or self.state in ["draft", "sent"]:
            return super()._is_paid()

        return True
