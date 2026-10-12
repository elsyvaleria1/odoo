from datetime import timedelta
from typing import Self

from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog
from odoo.tools import frozendict

from odoo.addons.sale_subscription.models.sale_order import (
    SUBSCRIPTION_CLOSED_STATE,
    SUBSCRIPTION_PROGRESS_STATE,
    SUBSCRIPTION_STATES,
)

_debug = DebugLog(__name__)


class SaleOrderLog(models.Model):
    _name = "sale.order.log"
    _description = "Sale Order Log"
    _order = "id desc"
    _access_anchors = frozendict(
        {
            "company": models.Anchor("company_id", shared=False),
        }
    )

    order_id = fields.Many2one(
        comodel_name="sale.order",
        string="Sale Order",
        index=True,
        readonly=True,
        required=True,
        ondelete="cascade",
        bypass_search_access=True,
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        related="order_id.user_id",
        string="Salesperson",
        depends=[],
    )
    team_id = fields.Many2one(
        comodel_name="team.team",
        related="order_id.team_id",
        string="Sales Team",
        depends=[],
        domain=[("use_sale", "=", True)],
    )
    plan_id = fields.Many2one(
        comodel_name="sale.subscription.plan",
        related="order_id.plan_id",
        string="Recurring Plan",
        depends=[],
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        related="order_id.company_id",
        string="Company",
        depends=[],
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        related="order_id.currency_id",
        string="Currency",
        depends=[],
        readonly=False,
    )
    origin_order_id = fields.Many2one(
        comodel_name="sale.order",
        string="Origin Contract",
        compute="_compute_origin_order_id",
        precompute=True,
        store=True,
        index=True,
    )

    event_type = fields.Selection(
        selection=[
            ("0_creation", "New"),
            ("1_expansion", "Expansion"),
            ("15_contraction", "Contraction"),
            ("2_churn", "Churn"),
            ("3_transfer", "Transfer"),
        ],
        string="Type of event",
        index=True,
        readonly=True,
        required=True,
    )
    event_date = fields.Date(
        default=fields.Date.today,
        index=True,
        required=True,
    )
    date_effective = fields.Date(index=True)
    recurring_monthly = fields.Monetary(
        string="New MRR",
        readonly=True,
        required=True,
        help="MRR, after applying the changes of that particular event",
    )
    amount_signed = fields.Monetary(
        string="MRR change",
        readonly=True,
        required=True,
    )
    subscription_state = fields.Selection(
        selection=SUBSCRIPTION_STATES,
        help="Subscription stage when the change occurred",
    )

    @api.depends("order_id")
    def _compute_origin_order_id(self) -> None:
        for log in self:
            log.origin_order_id = log.order_id.origin_order_id or log.order_id

    def _compute_display_name(self):
        for log in self:
            log.display_name = self.env._("Sale order log: %s", log.id)

    @api.model
    def _create_log(self, order, initial_values):
        old_state = (
            initial_values.get("subscription_state", order.subscription_state)
            or "1_draft"
        )
        new_state = order.subscription_state
        _debug.logic(
            "mrr_log_dispatch", order=order, old=old_state, new=new_state or "none"
        )

        if (
            order.state == "cancel"
            and order.subscription_id
            and old_state in SUBSCRIPTION_PROGRESS_STATE + SUBSCRIPTION_CLOSED_STATE
        ):
            return self._cancel_renewal_logs(order, initial_values)

        if order.state == "cancel":
            return self._cancel_logs(order, initial_values)

        if new_state in SUBSCRIPTION_PROGRESS_STATE and old_state == "1_draft":
            return self._create_creation_log(order, initial_values)

        if new_state in SUBSCRIPTION_PROGRESS_STATE and old_state == "2_renewal":
            return self._create_renewal_transfer_log(order, initial_values)

        if new_state in SUBSCRIPTION_PROGRESS_STATE and old_state == "6_churn":
            return self._unlink_churn_log(order, initial_values)

        if old_state in SUBSCRIPTION_PROGRESS_STATE and new_state == "6_churn":
            return self._create_churn_log(order, initial_values)

        if (
            new_state not in SUBSCRIPTION_PROGRESS_STATE
            and old_state not in SUBSCRIPTION_PROGRESS_STATE
        ):
            return self.env["sale.order.log"]

        if (
            "currency_id" in initial_values
            and initial_values["currency_id"] != order.currency_id
        ):
            return self._create_currency_transfer_log(order, initial_values)

        return self._create_mrr_change_log(order, initial_values)

    @api.model
    def _cancel_renewal_logs(self, order, initial_values):
        order.order_log_ids.unlink()
        transfer_log = self.search(
            [
                ("order_id", "=", order.subscription_id.id),
                ("event_type", "=", "3_transfer"),
                ("amount_signed", "<", 0),
            ],
            order="id desc",
            limit=1,
        )
        order.subscription_id.order_log_ids.filtered(
            lambda log: log.date_effective in transfer_log.mapped("date_effective")
        ).date_effective = False
        _debug.lifecycle(
            "renewal_logs_cancelled", order=order, transfer_log=transfer_log
        )
        transfer_log.unlink()
        return self.env["sale.order.log"]

    @api.model
    def _cancel_logs(self, order, initial_values):
        _debug.lifecycle("order_logs_cancelled", order=order, logs=order.order_log_ids)
        order.order_log_ids.unlink()
        return self.env["sale.order.log"]

    @api.model
    def _create_creation_log(self, order, initial_values) -> Self:
        return self.create(
            {
                "order_id": order.id,
                "event_type": "0_creation",
                "amount_signed": max(order.recurring_monthly, 0),
                "recurring_monthly": max(order.recurring_monthly, 0),
                "subscription_state": initial_values.get("subscription_state")
                or "1_draft",
            }
        )

    @api.model
    def _create_renewal_transfer_log(self, order, initial_values):
        result = self.env["sale.order.log"]
        parent_order = order.subscription_id
        parent_churn = parent_order.order_log_ids.filtered(
            lambda log: log.event_type == "2_churn"
        )

        if parent_order.next_invoice_date + timedelta(days=30) < order.start_date:
            if not parent_churn:
                result += self._create_churn_log(parent_order, {})
            return result + self._create_creation_log(order, initial_values)

        parent_churn[:1].unlink()

        parent_transfer_amount = sum(parent_order.order_log_ids.mapped("amount_signed"))
        parent_transfer = self.create(
            {
                "order_id": parent_order.id,
                "event_type": "3_transfer",
                "amount_signed": -parent_transfer_amount,
                "recurring_monthly": 0,
                "subscription_state": parent_order.subscription_state,
            }
        )
        parent_order.order_log_ids.filtered(
            lambda log: not log.date_effective
        ).date_effective = parent_order.next_invoice_date

        renewal_transfer_amount = parent_transfer.currency_id._convert(
            parent_transfer_amount,
            to_currency=order.currency_id,
            company=order.company_id,
            round=False,
        )
        renewal_transfer = self.create(
            {
                "order_id": order.id,
                "event_type": "3_transfer",
                "amount_signed": renewal_transfer_amount,
                "recurring_monthly": renewal_transfer_amount,
                "subscription_state": initial_values.get(
                    "subscription_state", order.subscription_state
                ),
            }
        )

        initial_values["recurring_monthly"] = renewal_transfer_amount
        return (
            parent_transfer
            + renewal_transfer
            + self._create_mrr_change_log(order, initial_values)
        )

    @api.model
    def _unlink_churn_log(self, order, initial_values):
        churn_logs = order.order_log_ids.filtered(
            lambda log: log.event_type == "2_churn"
        )
        effective_at_churn = order.order_log_ids.filtered(
            lambda log: log.date_effective in churn_logs.mapped("date_effective")
        )
        effective_at_churn.date_effective = False
        churn_logs.unlink()
        initial_values["recurring_monthly"] = sum(
            order.order_log_ids.mapped("amount_signed")
        )
        return self._create_mrr_change_log(order, initial_values)

    @api.model
    def _create_churn_log(self, order, initial_values) -> Self:
        order.order_log_ids.filtered(
            lambda log: not log.date_effective
        ).date_effective = order.next_invoice_date
        return self.create(
            {
                "order_id": order.id,
                "event_type": "2_churn",
                "amount_signed": -sum(order.order_log_ids.mapped("amount_signed")),
                "recurring_monthly": 0,
                "subscription_state": initial_values.get(
                    "subscription_state", order.subscription_state
                ),
                "date_effective": order.next_invoice_date,
            }
        )

    @api.model
    def _create_currency_transfer_log(self, order, initial_values):
        new_mrr = max(order.recurring_monthly, 0)
        old_mrr = max(initial_values.get("recurring_monthly", new_mrr), 0)
        old_mrr_new_currency = initial_values["currency_id"]._convert(
            old_mrr,
            to_currency=order.currency_id,
            company=order.company_id,
            round=False,
        )
        result = self.create(
            [
                {
                    "order_id": order.id,
                    "event_type": "3_transfer",
                    "amount_signed": -old_mrr,
                    "currency_id": initial_values["currency_id"].id,
                    "recurring_monthly": 0,
                    "subscription_state": initial_values.get(
                        "subscription_state", order.subscription_state
                    ),
                },
                {
                    "order_id": order.id,
                    "event_type": "3_transfer",
                    "amount_signed": old_mrr_new_currency,
                    "recurring_monthly": old_mrr_new_currency,
                    "subscription_state": initial_values.get(
                        "subscription_state", order.subscription_state
                    ),
                },
            ]
        )

        if old_mrr_new_currency != new_mrr:
            initial_values["recurring_monthly"] = old_mrr_new_currency
            result += self._create_mrr_change_log(order, initial_values)

        return result

    @api.model
    def _create_mrr_change_log(self, order, initial_values):
        new_mrr = max(order.recurring_monthly, 0)
        old_mrr = max(initial_values.get("recurring_monthly", new_mrr), 0)

        if order.currency_id.compare_amounts(old_mrr, new_mrr) == 0:
            return self.env["sale.order.log"]

        return self.create(
            {
                "order_id": order.id,
                "event_type": "1_expansion" if new_mrr > old_mrr else "15_contraction",
                "amount_signed": new_mrr - old_mrr,
                "recurring_monthly": new_mrr,
                "subscription_state": order.subscription_state,
            }
        )

    @api.model
    def _update_date_effective(self, log_date_values) -> None:
        self._write_uninvoiced_logs(log_date_values["subscription"])
        self._write_uninvoiced_logs(log_date_values["upsell"], upsell=True)
        self.env.flush_all()

    def _write_uninvoiced_logs(self, log_date_values, upsell=False) -> None:
        if not log_date_values:
            return

        for order, dates in log_date_values.items():
            if upsell:
                ratio = order._get_ratio_value()
                amount = sum(line.recurring_monthly / ratio for line in order.line_ids)
                logs = order.subscription_id.order_log_ids.filtered_domain(
                    [
                        ("date_effective", "=", False),
                        ("event_date", "=", dates["event_date"]),
                    ]
                )._filtered_closest_to_amount(amount)
            else:
                logs = order.order_log_ids.filtered(lambda log: not log.date_effective)

            logs.sudo().date_effective = dates["date_effective"]

    def _filtered_closest_to_amount(self, amount):
        return self.sorted(lambda log: abs(log.amount_signed - amount))[:1]
