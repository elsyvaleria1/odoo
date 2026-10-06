from odoo import fields, models
from odoo.db.schema import drop_view_if_exists
from odoo.libs.debug_log import DebugLog
from odoo.tools import frozendict

_debug = DebugLog(__name__)


def nlargest(amount, data_list, method):
    return sorted(data_list, key=method, reverse=1)[:amount]


class HrRecruitmentReport(models.Model):
    _name = "hr.recruitment.report"
    _description = "Recruitment Analysis Report"
    _auto = False
    _depends = frozendict(
        {
            "calendar.event": ["applicant_id"],
            "hr.applicant": [
                "active",
                "company_id",
                "create_date",
                "create_uid",
                "date_closed",
                "job_id",
                "medium_id",
                "partner_name",
                "refuse_reason_id",
                "source_id",
                "stage_id",
                "user_id",
            ],
        }
    )
    _rec_name = "create_date"
    _order = "create_date desc"

    count = fields.Integer(
        string="Applications",
        readonly=True,
        aggregator="sum",
    )
    refused = fields.Integer(
        readonly=True,
        aggregator="sum",
    )
    hired = fields.Integer(
        readonly=True,
        aggregator="sum",
    )
    hiring_ratio = fields.Integer(
        string="Hired Ratio",
        readonly=True,
        aggregator="avg",
    )
    meetings_amount = fields.Integer(
        string="Meetings",
        readonly=True,
        aggregator="sum",
    )
    in_progress = fields.Integer(
        readonly=True,
        aggregator="sum",
    )

    state = fields.Selection(
        selection=[
            ("in_progress", "In Progress"),
            ("is_hired", "Hired"),
            ("refused", "Refused"),
        ],
        readonly=True,
    )

    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Recruiter",
        readonly=True,
    )
    create_date = fields.Date(
        string="Application Date",
        readonly=True,
    )
    create_uid = fields.Many2one(
        comodel_name="res.users",
        string="Creator",
        readonly=True,
    )
    date_closed = fields.Date(
        string="End Date",
        readonly=True,
    )
    stage_id = fields.Many2one(
        comodel_name="hr.recruitment.stage",
        readonly=True,
    )

    name = fields.Char(
        string="Applicant Name",
        readonly=True,
    )
    job_id = fields.Many2one(
        comodel_name="hr.job",
        readonly=True,
    )
    medium_id = fields.Many2one(
        comodel_name="utm.medium",
        readonly=True,
    )
    source_id = fields.Many2one(
        comodel_name="utm.source",
        readonly=True,
    )
    process_duration = fields.Integer(
        readonly=True,
        aggregator="avg",
    )
    refuse_reason_id = fields.Many2one(
        comodel_name="hr.applicant.refuse.reason",
        readonly=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        readonly=True,
    )

    def action_view_applicant(self) -> dict | None:
        self.check_singleton()
        return {
            "name": self.env._("Applicant"),
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": "hr.applicant",
            "res_id": self.id,
            "target": "current",
        }

    def _query(self, fields="", from_clause=""):
        select_ = (
            """
                a.id as id,
                a.user_id,
                a.create_date,
                a.create_uid,
                a.date_closed,
                a.stage_id,
                a.company_id,
                a.job_id,
                a.refuse_reason_id,
                a.medium_id,
                a.source_id,
                count(m.id) as meetings_amount,
                CASE
                    WHEN a.active IS FALSE THEN 'refused'
                    WHEN a.date_closed IS NOT NULL THEN 'is_hired'
                    ELSE 'in_progress'
                END AS state,
                a.partner_name as name,
                CASE WHEN a.refuse_reason_id IS NOT NULL OR a.active IS TRUE THEN 1 ELSE 0 END as count,
                CASE WHEN a.refuse_reason_id IS NOT NULL THEN 1 ELSE 0 END as refused,
                CASE WHEN a.refuse_reason_id IS NULL AND a.active IS TRUE AND a.date_closed IS NOT NULL THEN 1 ELSE 0 END as hired,
                CASE WHEN a.date_closed IS NOT NULL THEN 100 ELSE 0 END as hiring_ratio,
                CASE WHEN a.active IS NOT FALSE AND a.date_closed IS NULL THEN 1 ELSE 0 END as in_progress,
                CASE WHEN a.date_closed IS NOT NULL THEN date_part('day', a.date_closed - a.create_date) ELSE NULL END as process_duration
                %s
        """
            % fields
        )

        from_ = (
            """
                hr_applicant a
                %s
        """
            % from_clause
        )

        join_ = """
                calendar_event m
                ON a.id = m.applicant_id
                WHERE a.job_id IS NOT NULL
                GROUP BY a.id
        """
        return "(SELECT %s FROM %s LEFT OUTER JOIN %s)" % (select_, from_, join_)

    def init(self) -> None:
        _debug.lifecycle("recruitment_report_view_rebuilt", table=self._table)
        drop_view_if_exists(self.env.cr, self._table)
        with _debug.perf("recruitment_report.create_view", table=self._table):
            self.env.cr.execute(
                """CREATE or REPLACE VIEW %s as (%s)""" % (self._table, self._query())
            )

    def get_leaderboard(self) -> list:
        query = """
            SELECT
                COUNT (a.id) as count,
                p.name,
                AVG (CASE WHEN a.date_closed IS NOT NULL THEN 100 ELSE 0 END) as hiring_ratio,
                COUNT (m.id) as meetings_amount,
                SUM (CASE WHEN a.date_closed IS NOT NULL THEN 1 ELSE 0 END) as is_hired
            FROM hr_applicant a
            JOIN res_users u
            ON a.user_id = u.id
            JOIN res_partner p
            ON u.partner_id = p.id
            LEFT JOIN calendar_event m
            ON a.id = m.applicant_id
            WHERE a.company_id = ANY(%s)
            GROUP BY p.name
        """
        with _debug.perf(
            "recruitment_report.leaderboard",
            companies=len(self.env.context["allowed_company_ids"]),
        ) as span:
            self.env.cr.execute(query, [list(self.env.context["allowed_company_ids"])])
            result = self.env.cr.dictfetchall()
            span.set(recruiters=len(result))

        _debug.pipeline(
            "recruitment_leaderboard_built",
            recruiters=len(result),
            ranked=min(3, len(result)),
        )
        return [
            {
                "title": self.env._("Total applicants"),
                "ranking_list": [
                    {"name": x["name"], "score": x["count"]}
                    for x in nlargest(3, result, lambda x: x["count"])
                ],
            },
            {
                "title": self.env._("Total Meetings"),
                "ranking_list": [
                    {"name": x["name"], "score": x["meetings_amount"]}
                    for x in nlargest(3, result, lambda x: x["meetings_amount"])
                ],
            },
            {
                "title": self.env._("Total Hired"),
                "ranking_list": [
                    {"name": x["name"], "score": x["is_hired"]}
                    for x in nlargest(3, result, lambda x: x["is_hired"])
                ],
            },
            {
                "title": self.env._("Hiring ratio"),
                "ranking_list": [
                    {"name": x["name"], "score": str(round(x["hiring_ratio"], 1)) + "%"}
                    for x in nlargest(3, result, lambda x: x["hiring_ratio"])
                ],
            },
        ]
