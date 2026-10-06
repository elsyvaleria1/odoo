from odoo import api, fields, models
from odoo.fields import Command
from odoo.libs.debug_log import DebugLog

from odoo.addons.base.models.mixin_recurrence_interval import (
    REPEAT_UNIT_SELECTION,
)

# The shared cadence vocabulary, minus the one value this module does not bill
# on. Narrowed from the shared list rather than spelled again, so a unit added
# there is a decision here and not a silent divergence.
PLAN_UNIT_SELECTION = [pair for pair in REPEAT_UNIT_SELECTION if pair[0] != "day"]

_debug = DebugLog(__name__)


class SaleSubscriptionPlan(models.Model):
    _name = "sale.subscription.plan"
    _description = "Subscription Plan"
    _inherit = ["mixin.recurrence.interval"]
    _order = "sequence, id"

    active = fields.Boolean(default=True)
    name = fields.Char(
        translate=True,
        default="Monthly",
        required=True,
    )
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one(comodel_name="res.company")

    # The billing period is `mixin.recurrence.interval`'s cadence -- a plan bills
    # every N units the way a task repeats every N units. Use the
    # `billing_period` property below for the timedelta.
    repeat_interval = fields.Integer(
        string="Billing Period ",
        required=True,
    )
    repeat_unit = fields.Selection(
        selection=PLAN_UNIT_SELECTION,
        string="Unit",
        default="month",
        required=True,
    )

    billing_period_display = fields.Char(
        string="Billing Period",
        compute="_compute_billing_period_display",
        search="_search_billing_period_display",
    )
    billing_period_display_sentence = fields.Char(
        string="Billing Period Display",
        compute="_compute_billing_period_display_sentence",
    )

    billing_first_day = fields.Boolean(
        string="Align to Period Start",
        default=False,
        help="Align all subscription invoices on the first day of each billing period.",
    )

    # Self Service
    user_closable = fields.Boolean(
        string="Closable",
        default=False,
        help="Customer can close their subscriptions.",
    )
    user_extend = fields.Boolean(
        string="Renew",
        default=False,
        help="Customer can create a renewal quotation for their subscription.",
    )
    user_quantity = fields.Boolean(
        string="Add Products",
        default=False,
        help="Allow customers to create an Upsell quote to adjust the quantity of products in their subscription."
        'Only products that are listed as "optional products" can be modified.',
    )
    related_plan_id = fields.Many2many(
        comodel_name="sale.subscription.plan",
        relation="sale_subscription_plan_related_plan",
        column1="plan_id",
        column2="related_plan_id",
        string="Optional Plans",
        help="Allow your customers to switch from this plan to "
        "another on quotation (new subscription or renewal)",
    )
    user_closable_options = fields.Selection(
        selection=[("at_date", "At date"), ("end_of_period", "End of period")],
        string="Closeable Plan Options",
        default="at_date",
        required=True,
    )
    pausable_by_user = fields.Boolean(
        string="Pausable",
        default=False,
        help="Allow customers to temporarily pause their subscription for a specific period. Not available for postpaid subscriptions.",
    )

    # Invoicing
    auto_close_limit = fields.Integer(
        string="Automatic Closing",
        default=15,
        help="Subscriptions late in renewing (e.g., automatic payment is failing continuously,"
        "customer didn't pay, etc.) will be automatically closed after this period.",
    )

    auto_close_limit_display = fields.Char(
        string="Automatic Closing After",
        compute="_compute_auto_close_limit_display",
    )

    invoice_mail_template_id = fields.Many2one(
        comodel_name="mail.template",
        string="Invoice Email Template",
        default=lambda self: self.env.ref(
            "account.email_template_edi_invoice", raise_if_not_found=False
        ),
        domain=[("model", "=", "account.move")],
        help="Email template used to send invoicing email automatically.\n"
        "Leave it empty if you don't want to send email automatically.",
    )

    subscription_rule_ids = fields.One2many(
        comodel_name="product.pricelist.item",
        inverse_name="plan_id",
        string="Recurring Pricing",
        domain=[
            ("plan_id", "!=", None),
            "|",
            ("product_tmpl_id", "=", None),
            ("product_tmpl_id.active", "=", True),
        ],
    )

    # UX
    active_subs_count = fields.Integer(
        string="Subscriptions",
        compute="_compute_active_subs_count",
    )
    subscription_line_count = fields.Integer(
        string="Subscription Count",
        compute="_compute_active_subscription_line_count",
    )

    def write(self, vals):
        if "related_plan_id" in vals:
            old_related = {plan.id: plan.related_plan_id for plan in self}
        res = super().write(vals)
        if "related_plan_id" in vals:
            for plan in self:
                if to_remove := old_related[plan.id] - plan.related_plan_id:
                    to_remove.related_plan_id = [Command.unlink(plan.id)]
                if to_add := plan.related_plan_id - old_related[plan.id]:
                    to_add.related_plan_id = [Command.link(plan.id)]
        return res

    def _search_billing_period_display(self, operator, value):
        if operator != "in":
            return NotImplemented
        plan_ids = [
            plan.id
            for plan in self.env["sale.subscription.plan"].search([])
            if any(v in plan.billing_period_display for v in value)
        ]
        return [("id", "in", plan_ids.ids)]

    def _compute_active_subs_count(self) -> None:
        res = dict(
            self.env["sale.order"]._read_group(
                [
                    ("plan_id", "in", self.ids),
                    ("is_subscription", "=", True),
                    ("subscription_state", "in", ["3_progress", "4_paused"]),
                ],
                ["plan_id"],
                ["__count"],
            )
        )
        for plan in self:
            plan.active_subs_count = res.get(plan, 0)

    def _compute_active_subscription_line_count(self) -> None:
        domain = [
            ("order_id.is_subscription", "=", True),
            ("product_id.recurring_invoice", "=", True),
            ("subscription_plan_id", "in", self.ids),
            ("order_id.subscription_state", "in", ("3_progress", "4_paused")),
            ("display_type", "=", False),
        ]
        line_counts = dict(
            self.env["sale.order.line"]._read_group(
                domain,
                ["subscription_plan_id"],
                ["__count"],
            )
        )
        for plan in self:
            plan.subscription_line_count = line_counts.get(plan, 0)

    def action_view_active_sub(self) -> dict:
        return {
            "name": self.env._("Subscriptions"),
            "view_mode": "list,form",
            "domain": [
                ("plan_id", "in", self.ids),
                ("is_subscription", "=", True),
                ("subscription_state", "in", ["3_progress", "4_paused"]),
            ],
            "res_model": "sale.order",
            "type": "ir.actions.act_window",
        }

    def action_view_active_subscription_lines(self) -> dict:
        subscription_items_plan = (
            self.env["sale.order"]
            .search(
                [
                    ("plan_id", "in", self.ids),
                    ("is_subscription", "=", True),
                    ("subscription_state", "in", ["3_progress", "4_paused"]),
                ]
            )
            .line_ids.filtered(
                lambda line: not line.display_type and line.product_id.recurring_invoice
            )
        )
        return {
            "name": self.env._("Subscription Items"),
            "view_mode": "list",
            "views": [
                (
                    self.env.ref(
                        "sale_subscription.sale_subscription_sale_order_line_list"
                    ).id,
                    "list",
                )
            ],
            "search_view_id": [
                self.env.ref(
                    "sale_subscription.sale_subscription_sales_order_line_filter"
                ).id
            ],
            "domain": [("id", "in", subscription_items_plan.ids)],
            "context": {"create": False},
            "res_model": "sale.order.line",
            "type": "ir.actions.act_window",
        }

    @property
    def billing_period(self):
        """This plan's cadence as a timedelta, or False when it has none.

        The guard is this module's own: sixteen call sites read the period and
        treat "no plan" or "no period" as "does not recur", so an empty plan has
        to answer falsely rather than raise the way `_get_recurrence_delta`
        does on an empty recordset.
        """
        if not self.repeat_unit or not self.repeat_interval:
            return False
        return self._get_recurrence_delta()

    @api.depends_context("lang")
    @api.depends("repeat_interval", "repeat_unit")
    def _compute_billing_period_display(self) -> None:
        for plan in self:
            value = plan.repeat_interval
            if plan.repeat_unit == "week":
                plan.billing_period_display = (
                    self.env._("%s Weeks", value) if value > 1 else self.env._("1 Week")
                )
            elif plan.repeat_unit == "month":
                plan.billing_period_display = (
                    self.env._("%s Months", value)
                    if value > 1
                    else self.env._("1 Month")
                )
            elif plan.repeat_unit == "year":
                plan.billing_period_display = (
                    self.env._("%s Years", value) if value > 1 else self.env._("1 Year")
                )
            else:
                _debug.logic("billing_period_unit_invalid", plan=plan, kind="display")
                raise ValueError(f"Invalid Billing Period Unit {plan.repeat_unit!r}")

    @api.depends_context("lang")
    @api.depends("repeat_interval", "repeat_unit")
    def _compute_billing_period_display_sentence(self) -> None:
        for plan in self:
            value = plan.repeat_interval
            if plan.repeat_unit == "week":
                sentence = (
                    self.env._("per %d weeks", value)
                    if value > 1
                    else self.env._("per week")
                )
            elif plan.repeat_unit == "month":
                sentence = (
                    self.env._("per %d months", value)
                    if value > 1
                    else self.env._("per month")
                )
            elif plan.repeat_unit == "year":
                sentence = (
                    self.env._("per %d years", value)
                    if value > 1
                    else self.env._("per year")
                )
            else:
                _debug.logic("billing_period_unit_invalid", plan=plan, kind="sentence")
                raise ValueError(f"Invalid Billing Period Unit {plan.repeat_unit!r}")
            plan.billing_period_display_sentence = sentence

    @api.depends("auto_close_limit")
    def _compute_auto_close_limit_display(self) -> None:
        for plan in self:
            plan.auto_close_limit_display = self.env._("%s days", plan.auto_close_limit)
