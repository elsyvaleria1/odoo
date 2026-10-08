from odoo import fields, models
from odoo.db.schema import drop_view_if_exists
from odoo.libs.debug_log import DebugLog
from odoo.tools import frozendict

from odoo.addons.project.models.project_task import CLOSED_STATES

_debug = DebugLog(__name__)


class ProjectResourceReport(models.Model):
    _name = "project.resource.report"
    _description = "Resource Utilization"
    _auto = False
    _depends = frozendict(
        {
            "project.task": [
                "active",
                "company_id",
                "is_template",
                "project_id",
                "state",
            ],
            "resource.calendar": [
                "hours_per_week",
                "schedule_type",
                "two_weeks_calendar",
                "tz",
            ],
            "resource.calendar.attendance": [
                "calendar_id",
                "day_period",
                "dayofweek",
                "display_type",
                "hour_from",
                "hour_to",
                "week_type",
            ],
            "resource.reservation": [
                "active",
                "allocated_hours",
                "date_end",
                "date_start",
                "res_id",
                "res_model",
                "resource_calendar_id",
                "resource_id",
            ],
            "resource.resource": ["calendar_id", "tz", "user_id"],
        }
    )
    _order = "allocated_hours desc"

    user_id = fields.Many2one(
        comodel_name="res.users",
        readonly=True,
    )
    project_id = fields.Many2one(
        comodel_name="project.project",
        readonly=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        readonly=True,
    )
    allocated_hours = fields.Float(
        readonly=True,
        aggregator="sum",
    )
    task_count = fields.Integer(
        string="Open Tasks",
        readonly=True,
        aggregator="sum",
    )
    project_count = fields.Integer(
        string="Projects",
        readonly=True,
        aggregator="max",
    )
    is_overallocated = fields.Boolean(
        string="Overallocated",
        readonly=True,
        help="True when the user's busiest single week exceeds their working "
        "calendar's weekly capacity across all active projects. A reservation's "
        "hours are spread over the ISO weeks it covers, read in its resource's "
        "time zone, in proportion to the working time its calendar gives each "
        "week, or to the elapsed time when that calendar has no fixed hours in "
        "the span. A reservation with no end loads the week it starts. "
        "Falls back to 40h for a resource with no calendar.",
    )

    @_debug.perf.timed
    def init(self) -> None:
        _debug.lifecycle("view_rebuilt", table=self._table)
        drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                WITH reservations AS (
                    SELECT
                        rr.id AS reservation_id,
                        res.user_id,
                        t.project_id,
                        t.company_id,
                        t.id AS task_id,
                        rr.allocated_hours,
                        COALESCE(cal.hours_per_week, 40) AS weekly_capacity,
                        work_cal.id AS calendar_id,
                        work_cal.schedule_type = 'fully_fixed' AS is_fixed,
                        work_cal.two_weeks_calendar IS TRUE AS is_two_weeks,
                        (rr.date_start AT TIME ZONE 'UTC')
                            AT TIME ZONE COALESCE(res.tz, work_cal.tz, 'UTC')
                            AS local_start,
                        (rr.date_end AT TIME ZONE 'UTC')
                            AT TIME ZONE COALESCE(res.tz, work_cal.tz, 'UTC')
                            AS local_end
                    FROM resource_reservation rr
                    JOIN resource_resource res ON res.id = rr.resource_id
                    LEFT JOIN resource_calendar cal ON cal.id = res.calendar_id
                    LEFT JOIN resource_calendar work_cal
                           ON work_cal.id = COALESCE(
                                  rr.resource_calendar_id, res.calendar_id
                              )
                    JOIN project_task t
                         ON t.id = rr.res_id
                        AND rr.res_model = 'project.task'
                    WHERE rr.active
                      AND t.state <> ALL(%s)
                      AND t.project_id IS NOT NULL
                      AND t.is_template IS NOT TRUE
                      AND t.active = TRUE
                      AND res.user_id IS NOT NULL
                ),
                user_project AS (
                    SELECT
                        user_id,
                        project_id,
                        company_id,
                        SUM(allocated_hours) AS allocated_hours,
                        COUNT(DISTINCT task_id) AS task_count
                    FROM reservations
                    GROUP BY user_id, project_id, company_id
                ),
                spans AS (
                    SELECT *
                    FROM reservations
                    WHERE local_end > local_start
                ),
                working_time AS (
                    SELECT s.reservation_id,
                           DATE_TRUNC('week', d.day) AS week_start,
                           EXTRACT(EPOCH FROM
                               LEAST(s.local_end, d.day + a.hour_to * INTERVAL '1 hour')
                               - GREATEST(
                                   s.local_start, d.day + a.hour_from * INTERVAL '1 hour'
                               )
                           )::float / 3600 AS hours
                    FROM spans s
                    CROSS JOIN LATERAL generate_series(
                        DATE_TRUNC('day', s.local_start),
                        s.local_end,
                        INTERVAL '1 day'
                    ) AS d(day)
                    JOIN resource_calendar_attendance a
                      ON a.calendar_id = s.calendar_id
                     AND a.display_type IS NULL
                     AND a.day_period IS DISTINCT FROM 'lunch'
                     AND a.dayofweek::int = EXTRACT(ISODOW FROM d.day)::int - 1
                     AND (
                         NOT s.is_two_weeks
                         OR a.week_type
                            = ((d.day::date - DATE '0001-01-01') / 7 %% 2)::text
                     )
                    WHERE s.is_fixed
                      AND d.day + a.hour_to * INTERVAL '1 hour' > s.local_start
                      AND d.day + a.hour_from * INTERVAL '1 hour' < s.local_end
                ),
                -- a span meeting no fixed working hour is weighed by elapsed
                -- time, and one with no length loads the week it starts
                segments AS (
                    SELECT reservation_id, week_start, hours
                    FROM working_time
                    UNION ALL
                    SELECT s.reservation_id,
                           w.week_start,
                           EXTRACT(EPOCH FROM
                               LEAST(s.local_end, w.week_start + INTERVAL '7 days')
                               - GREATEST(s.local_start, w.week_start)
                           )::float / 3600
                    FROM spans s
                    CROSS JOIN LATERAL generate_series(
                        DATE_TRUNC('week', s.local_start),
                        s.local_end - INTERVAL '1 microsecond',
                        INTERVAL '7 days'
                    ) AS w(week_start)
                    WHERE NOT EXISTS (
                        SELECT 1 FROM working_time wt
                        WHERE wt.reservation_id = s.reservation_id
                    )
                    UNION ALL
                    SELECT reservation_id, DATE_TRUNC('week', local_start), 1.0
                    FROM reservations
                    WHERE local_start IS NOT NULL
                      AND (local_end IS NULL OR local_end <= local_start)
                ),
                week_loads AS (
                    SELECT r.user_id,
                           s.week_start,
                           r.weekly_capacity,
                           r.allocated_hours * SUM(s.hours)
                               / SUM(SUM(s.hours)) OVER (
                                   PARTITION BY s.reservation_id
                               ) AS hours
                    FROM segments s
                    JOIN reservations r ON r.reservation_id = s.reservation_id
                    GROUP BY s.reservation_id,
                             s.week_start,
                             r.user_id,
                             r.weekly_capacity,
                             r.allocated_hours
                ),
                user_peak AS (
                    SELECT user_id,
                           MAX(week_hours) AS peak_week_hours,
                           MAX(weekly_capacity) AS weekly_capacity
                    FROM (
                        SELECT user_id, week_start,
                               SUM(hours) AS week_hours,
                               MAX(weekly_capacity) AS weekly_capacity
                        FROM week_loads
                        GROUP BY user_id, week_start
                    ) w
                    GROUP BY user_id
                ),
                user_totals AS (
                    SELECT user_id, COUNT(DISTINCT project_id) AS project_count
                    FROM user_project
                    GROUP BY user_id
                )
                SELECT
                    ROW_NUMBER() OVER (ORDER BY up.user_id, up.project_id) AS id,
                    up.user_id,
                    up.project_id,
                    up.company_id,
                    up.allocated_hours,
                    up.task_count,
                    ut.project_count,
                    COALESCE(pk.peak_week_hours, 0)
                        > COALESCE(pk.weekly_capacity, 40) AS is_overallocated
                FROM user_project up
                JOIN user_totals ut ON ut.user_id = up.user_id
                LEFT JOIN user_peak pk ON pk.user_id = up.user_id
            )
            """,
            (list(CLOSED_STATES),),
        )
