from odoo import api, fields, models
from odoo.tools import frozendict


class PlanningAnalysisReport(models.Model):
    _name = "planning.analysis.report"
    _description = "Planning Analysis Report"
    _auto = False
    _depends = frozendict(
        {
            "hr.employee": ["current_version_id", "hourly_cost", "parent_id"],
            "hr.job": ["name"],
            "hr.version": ["date_version", "department_id", "employee_id", "job_id"],
            "planning.slot": [
                "allocated_hours",
                "allocated_percentage",
                "company_id",
                "employee_id",
                "end_datetime",
                "name",
                "publication_warning",
                "recurrency_id",
                "request_to_switch",
                "resource_id",
                "role_id",
                "start_datetime",
                "state",
            ],
            "res.company": ["currency_id"],
            "resource.resource": ["type", "user_id"],
        }
    )
    _access_anchors = frozendict(
        {
            "company": models.Anchor("company_id", shared=False),
            "owner": "user_id",
        }
    )

    allocated_hours = fields.Float(
        string="Allocated Time",
        readonly=True,
    )
    allocated_percentage = fields.Float(
        string="Allocated Time (%)",
        readonly=True,
        aggregator="avg",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        readonly=True,
    )
    department_id = fields.Many2one(
        comodel_name="hr.department",
        readonly=True,
    )
    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        readonly=True,
    )
    end_datetime = fields.Datetime(
        string="End Date",
        readonly=True,
    )
    job_title = fields.Char(readonly=True)
    manager_id = fields.Many2one(
        comodel_name="hr.employee",
        readonly=True,
    )
    name = fields.Text(
        string="Note",
        readonly=True,
    )
    publication_warning = fields.Boolean(
        string="Modified Since Last Publication",
        readonly=True,
        help="If checked, it means that the shift contains has changed since its last publish.",
    )
    recurrency_id = fields.Many2one(
        comodel_name="planning.recurrency",
        readonly=True,
    )
    resource_id = fields.Many2one(
        comodel_name="resource.resource",
        readonly=True,
    )
    resource_type = fields.Selection(
        selection=[
            ("human", "Human"),
            ("material", "Material"),
            ("intangible", "Intangible"),
        ],
        readonly=True,
    )
    role_id = fields.Many2one(
        comodel_name="resource.role",
        readonly=True,
    )
    start_datetime = fields.Datetime(
        string="Start Date",
        readonly=True,
    )
    state = fields.Selection(
        selection="_selection_slot_state",
        string="Status",
        readonly=True,
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        readonly=True,
    )
    slot_id = fields.Many2one(
        comodel_name="planning.slot",
        string="Planning Slot",
        readonly=True,
    )
    request_to_switch = fields.Boolean(
        string="Has there been a request to switch on this shift slot?",
        readonly=True,
    )

    @api.model
    def _selection_slot_state(self) -> list[tuple[str, str]]:
        return (
            self.env["planning.slot"]._fields["state"]._description_selection(self.env)
        )

    @property
    def _table_query(self):
        return "%s %s %s %s" % (
            self._select(),
            self._from(),
            self._join(),
            self._group_by(),
        )

    @api.model
    def _select(self):
        return """
            SELECT
                S.id AS id,
                S.id AS slot_id,
                S.allocated_hours AS allocated_hours,
                S.allocated_percentage AS allocated_percentage,
                S.company_id AS company_id,
                CV.department_id AS department_id,
                S.employee_id AS employee_id,
                S.end_datetime AS end_datetime,
                J.name AS job_title,
                E.parent_id AS manager_id,
                S.name AS name,
                S.publication_warning AS publication_warning,
                S.request_to_switch AS request_to_switch,
                S.resource_id AS resource_id,
                R.type AS resource_type,
                S.role_id AS role_id,
                S.recurrency_id AS recurrency_id,
                S.start_datetime AS start_datetime,
                S.state AS state,
                R.user_id AS user_id
        """

    @api.model
    def _from(self):
        return """
            FROM planning_slot S
        """

    @api.model
    def _join(self):
        return """
            LEFT JOIN hr_employee E ON E.id = S.employee_id
            LEFT JOIN (
                SELECT DISTINCT ON (employee_id) employee_id, job_id
                FROM hr_version
                ORDER BY employee_id, date_version DESC
            ) V ON V.employee_id = E.id
            LEFT JOIN hr_version CV ON CV.id = E.current_version_id
            LEFT JOIN hr_job J ON J.id = V.job_id
            LEFT JOIN resource_resource R ON R.id = S.resource_id
        """

    @api.model
    def _group_by(self):
        return """
            GROUP BY S.id,
                     S.allocated_hours,
                     S.allocated_percentage,
                     S.company_id,
                     CV.department_id,
                     S.employee_id,
                     S.end_datetime,
                     J.name,
                     E.parent_id,
                     S.name,
                     S.publication_warning,
                     S.resource_id,
                     R.type,
                     S.role_id,
                     S.recurrency_id,
                     S.start_datetime,
                     S.state,
                     R.user_id
        """
