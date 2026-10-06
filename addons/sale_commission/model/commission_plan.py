from dateutil.relativedelta import relativedelta

from odoo import Command, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.libs.datetime import start_of
from odoo.libs.debug_log import DebugLog
from odoo.libs.json import dumps as json_dumps
from odoo.tools import date_utils, format_date

_debug = DebugLog(__name__)


class SaleCommissionPlan(models.Model):
    _name = "sale.commission.plan"
    _description = "Commission Plan"
    _order = "id"
    _inherit = ["mixin.mail.thread"]

    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        required=True,
    )
    active = fields.Boolean(default=True)
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        related="company_id.currency_id",
    )

    name = fields.Char(required=True)

    date_from = fields.Date(
        string="From",
        default=lambda self: fields.Date.today() + relativedelta(day=1, month=1),
        required=True,
        tracking=True,
    )
    date_to = fields.Date(
        string="To",
        default=lambda self: (
            fields.Date.today()
            + relativedelta(years=1, day=1, month=1)
            - relativedelta(days=1)
        ),
        required=True,
        tracking=True,
    )
    periodicity = fields.Selection(
        selection=[("month", "Monthly"), ("quarter", "Quarterly"), ("year", "Yearly")],
        default="quarter",
        required=True,
        tracking=True,
    )

    commission_amount = fields.Monetary(
        string="On Target Commission",
        currency_field="currency_id",
        default=1000,
        help="OTC",
    )

    type = fields.Selection(
        selection=[("target", "Targets"), ("achieve", "Achievements")],
        default="achieve",
        required=True,
        tracking=True,
    )
    user_type = fields.Selection(
        selection=[("person", "Salesperson"), ("team", "Sales Team")],
        default="person",
        required=True,
        tracking=True,
    )
    team_id = fields.Many2one(
        comodel_name="team.team",
        string="Sale team",
        domain=[("use_sale", "=", True)],
    )

    achievement_ids = fields.One2many(
        comodel_name="sale.commission.plan.achievement",
        inverse_name="plan_id",
        default=[Command.create({"type": "amount_invoiced"})],
        copy=True,
    )
    target_ids = fields.One2many(
        comodel_name="sale.commission.plan.target",
        inverse_name="plan_id",
        compute="_compute_targets",
        store=True,
        copy=True,
        readonly=False,
    )
    target_commission_ids = fields.One2many(
        comodel_name="sale.commission.plan.target.commission",
        inverse_name="plan_id",
        compute="_compute_target_commission_ids",
        inverse="_inverse_target_commission_ids",
        store=True,
        copy=True,
        readonly=False,
    )
    target_commission_graph = fields.Text(compute="_compute_target_commission_graph")
    user_ids = fields.One2many(
        comodel_name="sale.commission.plan.user",
        inverse_name="plan_id",
        copy=True,
    )

    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("approved", "Approved"),
            ("done", "Done"),
            ("cancel", "Cancelled"),
        ],
        default="draft",
        required=True,
        tracking=True,
    )

    def init(self) -> None:
        self.env.cr.execute("""
CREATE INDEX IF NOT EXISTS sale_order_team_id_date_order_idx ON sale_order (team_id, date_order) WHERE state = 'done';
CREATE INDEX IF NOT EXISTS account_move_team_id_date_idx ON account_move (team_id, date) WHERE move_type IN ('out_invoice', 'out_refund');
CREATE INDEX IF NOT EXISTS account_move_invoice_user_id_date_idx ON account_move (invoice_user_id, date) WHERE move_type IN ('out_invoice', 'out_refund');
        """)
        super().init()

    @api.constrains("target_commission_ids")
    def _check_zero_achievement_target(self) -> None:
        for plan in self:
            if plan.type == "target" and not plan.target_commission_ids.filtered(
                lambda target: target.target_rate == 0
            ):
                _debug.logic("plan_rejected", plan=plan, reason="target_commissions")
                raise ValidationError(
                    self.env._(
                        "The plan should have at least one target with an achievement rate of 0%"
                    )
                )

    @api.constrains("date_from", "date_to")
    def _check_dates(self) -> None:
        for plan in self:
            if plan.date_to and plan.date_from and not plan.date_to > plan.date_from:
                _debug.logic("plan_rejected", plan=plan, reason="dates_inverted")
                raise ValidationError(
                    self.env._("The start date must be before the end date.")
                )

    @api.constrains("team_id", "user_type")
    def _check_team_id(self) -> None:
        for plan in self:
            if plan.user_type == "team" and not plan.team_id:
                _debug.logic("plan_rejected", plan=plan, reason="team_missing")
                raise ValidationError(self.env._("The team is required in team plan."))

    @api.model
    def _date2name(self, dt, periodicity):
        if periodicity == "month":
            return format_date(self.env, dt, date_format="MMM y")
        elif periodicity == "quarter":
            return f"{dt.year} Q{date_utils.get_quarter_number(dt)}"
        elif periodicity == "year":
            return dt.strftime("%Y")
        return ""

    @api.depends("periodicity", "date_from", "date_to", "type")
    def _compute_targets(self, amount=0) -> None:
        for plan in self:
            if not plan.date_from or not plan.date_to:
                continue
            date_from = plan.date_from
            if plan.periodicity == "month":
                timedelta = relativedelta(months=1, day=1)
                date_from = date_from - relativedelta(days=1) + timedelta
            elif plan.periodicity == "quarter":
                timedelta = relativedelta(months=3, day=1)
                quarter_start = start_of(date_from, "quarter")
                if quarter_start < date_from:
                    quarter_start += timedelta
                date_from = quarter_start
            else:
                timedelta = relativedelta(years=1, month=1, day=1)
                date_from = date_from - relativedelta(days=1) + timedelta

            match plan.periodicity:
                case "month":
                    expected_target_duration = range(27, 31)
                case "quarter":
                    expected_target_duration = range(89, 92)
                case "year":
                    expected_target_duration = range(364, 366)
            # Map existing targets and track changes, starting by unlinking out-of-range ones.
            existing_targets = {(t.date_from, t.date_to): t for t in plan.target_ids}
            target_changes = [
                Command.unlink(t.id)
                for t in plan.target_ids
                if (
                    t.date_from < plan.date_from or t.date_to > plan.date_to
                )  # Doesn't belong to updated period
                or (t.date_to - t.date_from).days
                not in expected_target_duration  # Doesn't belong to updated periodicity
            ]

            while date_from + timedelta - relativedelta(days=1) <= plan.date_to:
                # Add new targets for missing periods.
                period_end = date_from + timedelta - relativedelta(days=1)
                if (date_from, period_end) not in existing_targets:
                    target_changes += [
                        Command.create(
                            {
                                "name": self._date2name(date_from, plan.periodicity),
                                "date_from": date_from,
                                "date_to": period_end,
                                "amount": amount,
                            }
                        )
                    ]
                date_from += timedelta
            if target_changes:
                plan.target_ids = target_changes

    @api.depends("commission_amount", "type")
    def _compute_target_commission_ids(self) -> None:
        for plan in self:
            if plan.type != "target":
                continue
            if not plan.target_commission_ids:
                plan.target_commission_ids = [
                    Command.create(
                        {
                            "plan_id": plan.id,
                            "target_rate": 0,
                            "amount": 0,
                        }
                    ),
                    Command.create(
                        {
                            "plan_id": plan.id,
                            "target_rate": 0.5,
                            "amount": 0,
                        }
                    ),
                    Command.create(
                        {
                            "plan_id": plan.id,
                            "target_rate": 1,
                            "amount": plan.commission_amount or 1,
                            "amount_rate": 1,
                        }
                    ),
                ]
            else:
                for target in plan.target_commission_ids:
                    target.amount = target.amount_rate * plan.commission_amount

    def _inverse_target_commission_ids(self) -> None:
        for plan in self:
            sorted_amounts = {}
            sorted_rates = []
            exact_value = False
            for target in plan.target_commission_ids.sorted("target_rate"):
                sorted_amounts[target.target_rate] = target.amount
                sorted_rates.append(target.target_rate)
                if target.target_rate == 1 and target.amount:
                    plan.commission_amount = target.amount
                    exact_value = True
                    break
            if not exact_value:
                # Try to interpolate/extrapolate values at 100
                amount = self._get_completion_value(sorted_amounts, sorted_rates)
                if amount:
                    plan.commission_amount = amount

    @api.depends("target_commission_ids")
    def _compute_target_commission_graph(self) -> None:
        for plan in self:
            plan.target_commission_graph = json_dumps(plan._get_graph_data())

    def _get_graph_data(self) -> dict:
        self.check_singleton()
        values = []
        for target in self.target_commission_ids.sorted("target_rate"):
            values += [{"x": round(target.target_rate * 100), "y": target.amount}]
        if values:
            # For visual purpose: explain how values is computed outside of known bounds
            values += [{"x": values[-1]["x"] + 50, "y": values[-1]["y"]}]
        return {"values": values, "currency": self.currency_id.symbol}

    def action_view_commission(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "res_model": "sale.commission.report",
            "name": self.env._("Related commissions"),
            "views": [
                [
                    self.env.ref("sale_commission.sale_commission_report_view_list").id,
                    "list",
                ]
            ],
            "domain": [("plan_id", "=", self.id)],
        }

    @staticmethod
    def _extract_past_users(user_ids) -> list:
        today = fields.Date.today()
        return [
            user
            for user in user_ids
            if (len(user) == 3 and not user[2].get("date_to"))
            or user[2]["date_to"] >= today
        ]

    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        return [
            dict(
                vals,
                name=self.env._("%s (copy)", cp.name),
                user_ids=self._extract_past_users(vals.get("user_ids", [])),
            )
            for cp, vals in zip(self, vals_list, strict=False)
        ]

    def action_approve(self):
        _debug.lifecycle("plan_state", plans=self, state="approved")
        self.state = "approved"

    def action_draft(self):
        self.state = "draft"

    def action_done(self):
        _debug.lifecycle("plan_state", plans=self, state="done")
        self.state = "done"

    def action_cancel(self):
        _debug.lifecycle("plan_state", plans=self, state="cancelled")
        self.state = "cancel"

    def action_export_targets(self) -> dict:
        self.check_singleton()
        if self.type != "target":
            _debug.logic("target_export_refused", plans=self)
            raise UserError(
                self.env._(
                    "Exporting targets is only available for plans based on targets"
                )
            )
        return {
            "type": "ir.actions.act_url",
            "url": f"/sale_commission/export/targets/{self.id}",
            "target": "download",
        }

    @api.model
    def _get_completion_value(self, sorted_amounts, sorted_rates):
        """Interpolate/extrapolate the amount at 100% target completion.
        return: amount at 100% target completion
        """
        lowest_vals = [v for v in sorted_rates if v < 1]
        higher_vals = [v for v in sorted_rates if v > 1]
        # The plan has always a value at 0% completion
        low, high = None, None
        if lowest_vals and higher_vals:
            low = lowest_vals[-1]
            high = higher_vals[0]
        elif not higher_vals and len(lowest_vals) > 1:
            low = lowest_vals[-2]
            high = lowest_vals[-1]
        if not (low and high) or low == high:
            # No values or division by zero
            return None
        # y = ax + b
        return sorted_amounts[low] + (sorted_amounts[high] - sorted_amounts[low]) / (
            high - low
        ) * (1 - low)
