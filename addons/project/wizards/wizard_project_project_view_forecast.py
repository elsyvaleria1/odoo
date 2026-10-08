import random
from bisect import bisect_left
from datetime import UTC, date, datetime, time, timedelta
from itertools import accumulate

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL

from odoo.addons.project.models.project_task import DELIVERED_STATES

_debug = DebugLog(__name__)


class WizardProjectProjectViewForecast(models.TransientModel):
    _name = "wizard.project.project.view.forecast"
    _description = "Monte Carlo Forecast"

    SIMULATION_WEEK_CAP = 200
    SIMULATION_COUNT_MAX = 10_000
    HISTORY_WEEKS_MAX = 520

    project_id = fields.Many2one(
        comodel_name="project.project",
        default=lambda self: self.env.context.get("active_id"),
        required=True,
    )
    remaining_items = fields.Integer(
        compute="_compute_remaining_items",
        store=True,
        readonly=False,
        help="Number of tasks to complete. Defaults to open task count.",
    )
    simulation_count = fields.Integer(
        string="Simulations",
        default=1000,
        help="Number of Monte Carlo iterations (more = more accurate).",
    )
    weeks_of_history = fields.Integer(
        string="Weeks of History",
        default=12,
        help="How many weeks of throughput data to sample from.",
    )
    p50_weeks = fields.Float(
        string="50th Percentile (weeks)",
        digits=(5, 1),
        readonly=True,
    )
    p85_weeks = fields.Float(
        string="85th Percentile (weeks)",
        digits=(5, 1),
        readonly=True,
    )
    p95_weeks = fields.Float(
        string="95th Percentile (weeks)",
        digits=(5, 1),
        readonly=True,
    )
    result_text = fields.Text(
        string="Forecast Summary",
        readonly=True,
    )

    @api.depends("project_id")
    def _compute_remaining_items(self) -> None:
        for wiz in self:
            if wiz.project_id:
                wiz.remaining_items = wiz.project_id.open_task_count
            else:
                wiz.remaining_items = 0

    def _check_simulation_bounds(self) -> None:
        if not 1 <= self.simulation_count <= self.SIMULATION_COUNT_MAX:
            raise UserError(
                self.env._(
                    "The number of simulations must be between 1 and %(max)s.",
                    max=self.SIMULATION_COUNT_MAX,
                )
            )
        if not 1 <= self.weeks_of_history <= self.HISTORY_WEEKS_MAX:
            raise UserError(
                self.env._(
                    "The weeks of history must be between 1 and %(max)s.",
                    max=self.HISTORY_WEEKS_MAX,
                )
            )

    @_debug.perf.timed
    def action_run_forecast(self) -> dict:
        self.check_singleton()
        self._check_simulation_bounds()
        sim_count = self.simulation_count
        _debug.lifecycle(
            "forecast_started",
            project=self.project_id.id,
            remaining=self.remaining_items,
            sims=sim_count,
            weeks=self.weeks_of_history,
        )
        if not self.remaining_items or self.remaining_items <= 0:
            self.result_text = "No remaining items to forecast."
            return self._prepare_action_reopen()

        throughput = self._get_weekly_throughput()
        _debug.logic(
            "forecast_throughput", project=self.project_id.id, throughput=throughput
        )
        if not throughput or all(t == 0 for t in throughput):
            self.result_text = (
                "No historical throughput data available. "
                "Close some tasks to build forecasting data."
            )
            return self._prepare_action_reopen()

        results, truncated = self._get_simulated_weeks(
            throughput, self.remaining_items, sim_count, random.Random()
        )
        n = len(results)
        self.p50_weeks = results[int(n * 0.50)]
        self.p85_weeks = results[int(n * 0.85)]
        self.p95_weeks = results[int(n * 0.95)]
        _debug.logic(
            "forecast_result",
            project=self.project_id.id,
            p50=self.p50_weeks,
            p85=self.p85_weeks,
            p95=self.p95_weeks,
            truncated=truncated,
            sims=sim_count,
        )

        avg_tp = sum(throughput) / len(throughput)
        lines = [
            self.env._(
                "Based on %(weeks)s weeks of throughput data (%(sims)s simulations):",
                weeks=len(throughput),
                sims=sim_count,
            ),
            "",
            self.env._(
                "  50%% chance of finishing in %(p)s weeks or less",
                p=f"{self.p50_weeks:.0f}",
            ),
            self.env._(
                "  85%% chance of finishing in %(p)s weeks or less",
                p=f"{self.p85_weeks:.0f}",
            ),
            self.env._(
                "  95%% chance of finishing in %(p)s weeks or less",
                p=f"{self.p95_weeks:.0f}",
            ),
            "",
            self.env._("Remaining items: %(n)s", n=self.remaining_items),
            self.env._(
                "Historical throughput: %(lo)s-%(hi)s tasks/week (avg %(avg)s), "
                "including %(zeros)s week(s) with no delivery",
                lo=min(throughput),
                hi=max(throughput),
                avg=f"{avg_tp:.1f}",
                zeros=sum(1 for t in throughput if not t),
            ),
        ]
        if truncated:
            lines += [
                "",
                self.env._(
                    "WARNING: %(pct)s%% of simulations had not finished after "
                    "%(cap)s weeks and were cut short — the percentiles above "
                    "are optimistic lower bounds.",
                    pct=f"{100 * truncated / sim_count:.0f}",
                    cap=self.SIMULATION_WEEK_CAP,
                ),
            ]
        self.result_text = "\n".join(lines)
        return self._prepare_action_reopen()

    @api.model
    def _get_simulated_weeks(
        self,
        throughput: list[int],
        remaining: int,
        count: int,
        rng: random.Random,
    ) -> tuple[list[int], int]:
        cap = self.SIMULATION_WEEK_CAP
        results = []
        truncated = 0
        for _i in range(count):
            delivered = list(accumulate(rng.choices(throughput, k=cap)))
            weeks = bisect_left(delivered, remaining) + 1
            if weeks > cap:
                truncated += 1
                weeks = cap
            results.append(weeks)
        results.sort()
        return results, truncated

    @_debug.perf.timed
    def _get_weekly_throughput(self) -> list[int]:
        self.project_id.check_access("read")
        tz = self.env.tz
        local_now = fields.Datetime.now().replace(tzinfo=UTC).astimezone(tz)
        current_week = local_now.date() - timedelta(days=local_now.weekday())
        first_week = current_week - timedelta(weeks=self.weeks_of_history)

        def get_utc_start(day: date) -> datetime:
            return (
                datetime.combine(day, time.min, tzinfo=tz)
                .astimezone(UTC)
                .replace(tzinfo=None)
            )

        self.env["project.task"].flush_model(
            ["project_id", "state", "date_closed", "is_template"]
        )
        rows = self.env.execute_query(
            SQL(
                """
                SELECT DATE_TRUNC('week', timezone(%(tz)s, timezone('UTC', date_closed)))::date,
                       COUNT(*)
                  FROM project_task
                 WHERE project_id = %(project_id)s
                   AND state IN %(delivered_states)s
                   AND date_closed >= %(since)s
                   AND date_closed < %(until)s
                   AND is_template IS NOT TRUE
                 GROUP BY 1
                """,
                tz=str(tz),
                project_id=self.project_id.id,
                delivered_states=DELIVERED_STATES,
                since=get_utc_start(first_week),
                until=get_utc_start(current_week),
            )
        )
        closed_per_week = dict(rows)
        project_start = (
            self.project_id.create_date.replace(tzinfo=UTC).astimezone(tz).date()
            if self.project_id.create_date
            else first_week
        )
        project_week = project_start - timedelta(days=project_start.weekday())
        series_start = max(
            first_week, min(project_week, min(closed_per_week, default=project_week))
        )
        weeks = (current_week - series_start).days // 7
        _debug.logic(
            "forecast_weeks_bucketed",
            project=self.project_id.id,
            tz=str(tz),
            first=series_start,
            current=current_week,
            weeks=weeks,
        )
        return [
            closed_per_week.get(series_start + timedelta(weeks=offset), 0)
            for offset in range(weeks)
        ]

    def _prepare_action_reopen(self) -> dict:
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
