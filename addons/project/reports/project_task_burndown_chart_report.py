from collections.abc import Sequence
from typing import Any

from odoo import api, fields, models
from odoo.api import DomainType
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL, frozendict

from odoo.addons.base.models.resource_utils import filter_domain_leaf

_debug = DebugLog(__name__)

BUCKET_STEPS = {
    "day": "1 day",
    "week": "1 week",
    "month": "1 month",
    "quarter": "3 month",
    "year": "1 year",
}


class ProjectTaskBurndownChartReport(models.AbstractModel):
    _name = "project.task.burndown.chart.report"
    _description = "Burndown Chart"
    _auto = False
    _order = "date"
    _search_visibility_fields = ()
    _access_anchors = frozendict(
        {
            "owner": "user_ids",
        }
    )
    _depends = frozendict(
        {
            "mail.message": ["date", "message_type", "model", "res_id"],
            "mail.tracking.value": ["field_id", "mail_message_id", "old_value_integer"],
            "project.task": [
                "active",
                "create_date",
                "date_closed",
                "planned_hours",
                "project_id",
                "step_id",
            ],
        }
    )

    planned_hours = fields.Float(readonly=True)
    date = fields.Date(readonly=True)
    date_assign = fields.Datetime(
        string="Assignment Date",
        readonly=True,
    )
    date_end = fields.Date(
        string="Deadline",
        readonly=True,
    )
    date_last_status_change = fields.Date(
        string="Last Status Change",
        readonly=True,
    )
    state = fields.Selection(
        selection="_selection_task_state",
        readonly=True,
    )
    is_closed = fields.Selection(
        selection=[("closed", "Closed tasks"), ("open", "Open tasks")],
        string="Closing State",
        readonly=True,
    )
    milestone_id = fields.Many2one(
        comodel_name="project.milestone",
        readonly=True,
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Customer",
        readonly=True,
    )
    project_id = fields.Many2one(
        comodel_name="project.project",
        readonly=True,
    )
    step_id = fields.Many2one(
        comodel_name="project.workflow.step",
        readonly=True,
    )
    tag_ids = fields.Many2many(
        comodel_name="project.tags",
        relation="project_tags_project_task_rel",
        column1="project_task_id",
        column2="project_tags_id",
        string="Tags",
        readonly=True,
    )
    user_ids = fields.Many2many(
        comodel_name="res.users",
        relation="project_task_user_rel",
        column1="task_id",
        column2="user_id",
        string="Assignees",
        readonly=True,
    )

    @api.model
    def _selection_task_state(self) -> list[tuple[str, str]]:
        return (
            self.env["project.task"]._fields["state"]._description_selection(self.env)
        )

    @property
    def task_specific_fields(self) -> list[str]:
        return [
            "date_assign",
            "date_end",
            "date_last_status_change",
            "state",
            "milestone_id",
            "partner_id",
            "project_id",
            "step_id",
            "tag_ids",
            "user_ids",
        ]

    @_debug.perf.timed
    @api.model
    def _search(
        self,
        domain: list,
        offset: int = 0,
        limit: int | None = None,
        order: str | None = None,
        **kwargs: Any,
    ) -> Any:
        report_domain, task_domain = self._get_domains_report_and_task(domain)
        main_query = super()._search(
            report_domain,
            offset=offset,
            limit=limit,
            order=order,
            **kwargs,
        )
        task_query = self.env["project.task"]._search(task_domain, **kwargs)
        _debug.pipeline(
            "search_domains_split",
            report_domain=report_domain,
            task_domain=task_domain,
        )
        groupby = self.env.context.get(
            "project_task_burndown_chart_report_groupby",
            ["date:month", "step_id"],
        )
        self._check_bucket_interval(groupby)
        interval = self._get_bucket_interval(groupby)
        _debug.logic(
            "groupby_interval_resolved",
            groupby=groupby,
            interval=interval,
            series_step=BUCKET_STEPS[interval],
            tz=self.env.context.get("tz"),
        )
        main_query._tables[self._table] = self._get_step_history_sql(
            task_query, interval, main_query
        )
        return main_query

    @api.model
    def _get_bucket_interval(self, groupby: Sequence[str]) -> str:
        date_groupby = next((g for g in groupby if g.startswith("date")), "date")
        return date_groupby.partition(":")[2] or "month"

    @api.model
    def _get_bucket_sql(self, column: SQL, interval: str, query: Any) -> SQL:
        return self._read_group_groupby_temporal(
            column,
            self.env["project.task"]._fields["create_date"],
            interval,
            f"date:{interval}",
            self._table,
            query,
        )

    @api.model
    def _get_step_history_sql(self, task_query: Any, interval: str, query: Any) -> SQL:
        step = SQL.literal(BUCKET_STEPS[interval])
        return SQL(
            """
            (
              WITH task_ids AS %(task_ids)s,
              tasks AS (
                  SELECT pt.id, pt.project_id, pt.step_id, pt.planned_hours,
                         pt.create_date, pt.date_closed
                    FROM project_task pt
                   WHERE pt.active AND pt.id IN (SELECT id FROM task_ids)
              ),
              step_changes AS (
                  SELECT mm.res_id AS task_id, mm.id AS message_id, mm.date,
                         mtv.old_value_integer AS old_step_id
                    FROM mail_message mm
                    JOIN mail_tracking_value mtv
                      ON mtv.mail_message_id = mm.id AND mtv.field_id = %(field_id)s
                   WHERE mm.model = 'project.task'
                     AND mm.message_type = 'notification'
                     AND mm.res_id IN (SELECT id FROM tasks)
              ),
              step_periods AS (
                  SELECT sc.task_id,
                         COALESCE(
                             LAG(sc.date) OVER (PARTITION BY sc.task_id ORDER BY sc.message_id),
                             t.create_date
                         ) AS date_begin,
                         sc.date AS date_end,
                         pws.id AS step_id
                    FROM step_changes sc
                    JOIN tasks t ON t.id = sc.task_id
                    LEFT JOIN project_workflow_step pws ON pws.id = sc.old_step_id
                  UNION ALL
                  SELECT t.id, COALESCE(last_change.date, t.create_date), NULL, t.step_id
                    FROM tasks t
                    LEFT JOIN LATERAL (
                        SELECT sc.date
                          FROM step_changes sc
                         WHERE sc.task_id = t.id
                         ORDER BY sc.message_id DESC
                         LIMIT 1
                    ) AS last_change ON TRUE
              ),
              bucketed_periods AS (
                  SELECT t.project_id, sp.step_id, t.planned_hours,
                         %(bucket_begin)s AS bucket_begin,
                         COALESCE(%(bucket_end)s, %(bucket_now)s + %(step)s::interval) AS bucket_end,
                         %(bucket_closed)s AS bucket_closed
                    FROM step_periods sp
                    JOIN tasks t ON t.id = sp.task_id
              ),
              moves AS (
                  SELECT project_id, step_id, bucket_begin, bucket_end, bucket_closed,
                         count(*) AS task_count,
                         sum(planned_hours) AS planned_hours
                    FROM bucketed_periods
                   WHERE bucket_begin < bucket_end
                   GROUP BY project_id, step_id, bucket_begin, bucket_end, bucket_closed
              )
              SELECT row_number() OVER ()::bigint AS id,
                     m.project_id,
                     m.step_id,
                     m.planned_hours,
                     m.task_count,
                     CASE WHEN m.bucket_closed <= series.bucket
                          THEN 'closed' ELSE 'open'
                     END AS is_closed,
                     series.bucket::date AS date
                FROM moves m
                CROSS JOIN LATERAL generate_series(
                    m.bucket_begin, m.bucket_end - INTERVAL '1 day', %(step)s::interval
                ) AS series(bucket)
            )
            """,
            task_ids=task_query.subselect(),
            field_id=self.env["ir.model.fields"]._get("project.task", "step_id").id,
            bucket_begin=self._get_bucket_sql(
                SQL.identifier("sp", "date_begin"), interval, query
            ),
            bucket_end=self._get_bucket_sql(
                SQL.identifier("sp", "date_end"), interval, query
            ),
            bucket_now=self._get_bucket_sql(
                SQL("(now() AT TIME ZONE 'UTC')"), interval, query
            ),
            bucket_closed=self._get_bucket_sql(
                SQL.identifier("t", "date_closed"), interval, query
            ),
            step=step,
            to_flush=self.pool.depends_flush_fields(self),
        )

    @api.model
    def _check_group_by(self, groupby: Sequence[str]) -> None:
        if not any(gb.startswith("date") for gb in groupby) or not any(
            gb in ("step_id", "is_closed") for gb in groupby
        ):
            raise UserError(
                self.env._(
                    "The view must be grouped by date and by Workflow Step - Burndown chart or Is Closed - Burnup chart"
                )
            )
        self._check_bucket_interval(groupby)

    @api.model
    def _check_bucket_interval(self, groupby: Sequence[str]) -> None:
        interval = self._get_bucket_interval(groupby)
        if interval not in BUCKET_STEPS:
            raise UserError(
                self.env._(
                    "This chart groups dates by day, week, month, quarter or year, not by %(interval)s.",
                    interval=interval,
                )
            )

    @api.model
    def _get_domains_report_and_task(self, domain: list) -> tuple[list, list]:
        burndown_chart_specific_fields = list(
            set(self._fields) - set(self.task_specific_fields)
        )
        task_specific_domain = filter_domain_leaf(
            domain, lambda field: field not in burndown_chart_specific_fields
        )
        non_task_specific_domain = filter_domain_leaf(
            domain, lambda field: field not in self.task_specific_fields
        )
        return non_task_specific_domain, task_specific_domain

    def _read_group_select(self, aggregate_spec: str, query: Any) -> SQL:
        if aggregate_spec == "__count":
            return SQL("SUM(%s)", SQL.identifier(self._table, "task_count"))
        return super()._read_group_select(aggregate_spec, query)

    @_debug.perf.timed
    def _read_group(
        self,
        domain: DomainType,
        groupby: Sequence[str] = (),
        aggregates: Sequence[str] = (),
        having: DomainType | None = None,
        offset: int = 0,
        limit: int | None = None,
        order: str | None = None,
    ) -> list[tuple]:
        self._check_group_by(groupby)
        _debug.pipeline(
            "read_group",
            domain=domain,
            groupby=list(groupby),
            aggregates=list(aggregates),
        )
        self = self.with_context(project_task_burndown_chart_report_groupby=groupby)

        return super()._read_group(
            domain=domain,
            groupby=groupby,
            aggregates=aggregates,
            having=having,
            offset=offset,
            limit=limit,
            order=order,
        )
