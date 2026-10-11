import statistics

from odoo import api, fields, models
from odoo.db.schema import drop_view_if_exists
from odoo.libs.debug_log import DebugLog
from odoo.tools import frozendict

_debug = DebugLog(__name__)


class EsgEmployeeReport(models.Model):
    _name = "esg.employee.report"
    _description = "ESG Employee Report"
    _auto = False
    _depends = frozendict(
        {
            "hr.employee": [
                "active",
                "company_id",
                "current_version_id",
                "parent_id",
                "private_address_id",
            ],
            "hr.version": [
                "contract_type_id",
                "department_id",
                "job_id",
                "resource_calendar_id",
                "wage",
                "work_location_id",
            ],
            "res.company": ["partner_id"],
            "res.partner": ["country_id", "gender"],
            "resource.calendar": ["full_time_required_hours", "hours_per_week"],
        }
    )

    def _get_sex_selection(self):
        return self.env["hr.employee"]._fields["sex"]._description_selection(self.env)

    count = fields.Integer(readonly=True)
    sex = fields.Selection(
        selection=_get_sex_selection,
        readonly=True,
        groups="hr.group_hr_user",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        readonly=True,
    )
    department_id = fields.Many2one(
        comodel_name="hr.department",
        readonly=True,
    )
    is_team_leader = fields.Boolean(
        readonly=True,
        groups="hr.group_hr_user",
    )
    is_full_time = fields.Boolean(
        readonly=True,
        groups="hr.group_hr_user",
    )
    leadership_level = fields.Integer(
        readonly=True,
        groups="hr.group_hr_user",
    )
    country_id = fields.Many2one(
        comodel_name="res.country",
        readonly=True,
    )
    wage = fields.Float(
        readonly=True,
        aggregator="avg",
        groups="hr.group_hr_manager",
    )
    job_id = fields.Many2one(
        comodel_name="hr.job",
        string="Job Position",
        readonly=True,
        groups="hr.group_hr_user",
    )
    contract_type_id = fields.Many2one(
        comodel_name="hr.contract.type",
        readonly=True,
        groups="hr.group_hr_manager",
    )

    def _select(self):
        return """
            e.id,
            home.gender AS sex,
            e.company_id,
            v.department_id,
            v.work_location_id,
            1 AS count,
            CASE
                WHEN COUNT(ee.id) > 0 THEN TRUE
                ELSE FALSE
            END AS is_team_leader,
            CASE
                WHEN rc.full_time_required_hours IS NULL
                    OR rc.hours_per_week = rc.full_time_required_hours
                THEN TRUE
                ELSE FALSE
            END as is_full_time,
            MAX(ll.level) AS leadership_level,
            comprp.country_id,
            v.wage,
            v.job_id,
            v.contract_type_id
        """

    def _from(self):
        return f"""
            hr_employee e
                LEFT JOIN res_partner home ON home.id = e.private_address_id
                LEFT JOIN hr_version v ON v.id = e.current_version_id
                LEFT JOIN hr_employee ee ON e.id = ee.parent_id
                LEFT JOIN resource_calendar rc ON v.resource_calendar_id = rc.id
                LEFT JOIN ({self._leadership_level_subquery()}) ll ON e.id = ll.employee_id
                LEFT JOIN res_company rcomp ON e.company_id = rcomp.id
                LEFT JOIN res_partner comprp ON rcomp.partner_id = comprp.id
        """

    def _where(self):
        return """
            e.active = TRUE
        """

    def _group_by(self):
        return """
            e.id,
            home.gender,
            e.company_id,
            v.department_id,
            v.work_location_id,
            rc.full_time_required_hours,
            rc.hours_per_week,
            ll.level,
            comprp.country_id,
            v.wage,
            v.job_id,
            v.contract_type_id
        """

    def _leadership_level_subquery(self) -> str:
        return """
            WITH RECURSIVE leadership_level AS (
                SELECT
                    e.id AS employee_id,
                    0 AS level,
                    ARRAY[e.id] AS visited_nodes  -- Track the path to detect cycles
                FROM hr_employee e

                UNION ALL

                SELECT
                    e.parent_id AS employee_id,  -- Move up to the manager
                    lh.level + 1,
                    lh.visited_nodes || e.parent_id  -- Add the new node to visited list
                FROM hr_employee e
                JOIN leadership_level lh ON e.id = lh.employee_id
                WHERE e.parent_id IS NOT NULL
                AND NOT e.parent_id = ANY(lh.visited_nodes)  -- Prevent cycles
            )
            SELECT
                employee_id,
                MAX(level) AS level
            FROM leadership_level
            GROUP BY employee_id
        """

    def init(self) -> None:
        if _debug.lifecycle.enabled:
            _debug.lifecycle(
                "esg_employee_report_view_rebuilt",
                table=self._table,
                group_by_columns=len(self._group_by().split(",")),
            )
        drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                  SELECT {self._select()}
                    FROM {self._from()}
                   WHERE {self._where()}
                GROUP BY {self._group_by()}
            )
        """)

    @api.model
    def get_overall_pay_gap(self):
        if _debug.logic.enabled:
            _debug.logic(
                "esg_pay_gap_requested",
                user=self.env.user,
                companies=self.env.companies,
                is_hr_user=self.env.user.has_group("hr.group_hr_user"),
                is_hr_manager=self.env.user.has_group("hr.group_hr_manager"),
            )
        if not self.env.user.has_group("hr.group_hr_user"):
            return None
        emp_by_sex = dict(
            self.env["hr.employee"]._read_group(
                domain=[("company_id", "in", self.env.companies.ids)],
                groupby=["sex"],
                aggregates=["id:recordset"],
            )
        )
        male_employees = emp_by_sex.get("male", self.env["hr.employee"])
        female_employees = emp_by_sex.get("female", self.env["hr.employee"])

        def get_wages(employees):
            return [
                wage
                for emp in employees
                if (wage := emp.version_id.sudo()._get_normalized_wage())
            ]

        male_wages = get_wages(male_employees)
        female_wages = get_wages(female_employees)

        male_median = statistics.median(male_wages) if male_wages else 0
        female_median = statistics.median(female_wages) if female_wages else 0

        if not male_median or not female_median:
            _debug.logic(
                "esg_pay_gap_not_computable",
                reason="no_male_wage" if not male_median else "no_female_wage",
                male_employees=len(male_employees),
                female_employees=len(female_employees),
                classified=len(male_employees) + len(female_employees),
                male_wages=len(male_wages),
                female_wages=len(female_wages),
            )
            return False

        if _debug.logic.enabled:
            _debug.logic(
                "esg_pay_gap_computed",
                male_employees=len(male_employees),
                female_employees=len(female_employees),
                male_wages=len(male_wages),
                female_wages=len(female_wages),
                male_median=male_median,
                female_median=female_median,
                gap_percent=round((male_median - female_median) / male_median * 100, 2),
            )
        return round((male_median - female_median) / male_median * 100, 2)
