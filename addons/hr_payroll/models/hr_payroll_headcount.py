from collections import defaultdict

from odoo import Command, api, fields, models
from odoo.tools import frozendict


class HrPayrollHeadcount(models.Model):
    _name = "hr.payroll.headcount"
    _description = "Payroll Headcount"
    _access_anchors = frozendict(
        {
            "company": models.Anchor("company_id", shared=False),
        }
    )

    name = fields.Char(
        compute="_compute_name",
        store=True,
    )
    is_name_custom = fields.Boolean(
        string="Custom Name",
        compute="_compute_is_name_custom",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company.id,
    )
    line_ids = fields.One2many(
        comodel_name="hr.payroll.headcount.line",
        inverse_name="headcount_id",
    )
    employee_count = fields.Count(
        count_of="line_ids",
        store=True,
    )
    date_from = fields.Date(
        string="From",
        default=lambda self: fields.Date.today(),
        required=True,
    )
    date_to = fields.Date(string="To")

    _date_range = models.Constraint(
        "CHECK (date_from <= date_to)",
        "The start date must be anterior to the end date.",
    )

    @api.depends("date_from", "date_to", "company_id")
    def _compute_name(self):
        for headcount in self:
            if not headcount.is_name_custom:
                headcount.name = headcount.get_default_name()

    @api.depends("name")
    def _compute_is_name_custom(self) -> None:
        for headcount in self:
            if headcount.name and headcount.name != headcount.get_default_name():
                headcount.is_name_custom = True
            else:
                headcount.is_name_custom = False

    def get_default_name(self) -> str:
        self.check_singleton()
        if self.date_from == self.date_to or not self.date_to:
            return self.env._(
                "Headcount for %(company_name)s on the %(date)s",
                company_name=self.company_id.name,
                date=self.date_from,
            )
        return self.env._(
            "Headcount for %(company_name)s from %(date_from)s to %(date_to)s",
            company_name=self.company_id.name,
            date_from=self.date_from,
            date_to=self.date_to,
        )

    def action_populate(self):
        self.check_singleton()
        if not self.date_to:
            self.date_to = self.date_from
        versions = self.env["hr.version"].search(
            [
                ("company_id", "=", self.company_id.id),
                "|",
                ("contract_date_end", "=", False),
                ("contract_date_end", ">=", self.date_from),
                ("contract_date_start", "!=", False),
                ("contract_date_start", "<=", self.date_to),
            ],
            order="employee_id, contract_date_start DESC",
        )

        versions_by_employee_id = defaultdict(lambda: self.env["hr.version"])
        working_rates = set()
        for version in versions:
            versions_by_employee_id[version.employee_id.id] |= version
            working_rates.add(round(version.hours_per_week, 2))

        existing_working_rates = self.env["hr.payroll.headcount.working.rate"].search(
            [("rate", "in", list(working_rates))]
        )
        working_rate_to_create = working_rates - set(
            existing_working_rates.mapped("rate")
        )
        if working_rate_to_create:
            created_working_rate = self.env["hr.payroll.headcount.working.rate"].create(
                [{"rate": rate} for rate in working_rate_to_create]
            )
            existing_working_rates |= created_working_rate

        working_rate_id_by_value = {}
        for working_rate in existing_working_rates:
            working_rate_id_by_value[working_rate.rate] = working_rate.id

        lines = [
            (
                0,
                0,
                {
                    "version_id": versions[0].id,
                    "working_rate_ids": [
                        Command.set(
                            [
                                working_rate_id_by_value[
                                    round(version.hours_per_week, 2)
                                ]
                                for version in versions
                            ]
                        ),
                    ],
                    "version_names": ", ".join(
                        version.name or version.employee_id.name for version in versions
                    ),
                },
            )
            for versions in versions_by_employee_id.values()
        ]
        self.line_ids = [Command.clear()] + lines

    def action_view_lines(self):
        self.check_singleton()
        return {
            "name": self.env._("Headcount's employees"),
            "type": "ir.actions.act_window",
            "res_model": "hr.payroll.headcount.line",
            "view_mode": "list",
            "domain": [("headcount_id", "=", self.id)],
            "target": "current",
            "context": {
                "search_default_group_by_department": True,
            },
        }


class HrPayrollHeadcountLine(models.Model):
    _name = "hr.payroll.headcount.line"
    _description = "Headcount Line"

    headcount_id = fields.Many2one(
        comodel_name="hr.payroll.headcount",
        string="headcount_id",
        index=True,
        required=True,
        ondelete="cascade",
    )
    working_rate_ids = fields.Many2many(
        comodel_name="hr.payroll.headcount.working.rate",
        required=True,
    )
    version_names = fields.Char(
        readonly=True,
        required=True,
    )
    version_id = fields.Many2one(
        comodel_name="hr.version",
        string="Employee Record",
        readonly=True,
        required=True,
    )
    department_id = fields.Many2one(
        related="version_id.department_id",
        string="Department",
    )
    job_id = fields.Many2one(
        related="version_id.job_id",
        string="Job Title",
    )
    currency_id = fields.Many2one(
        related="version_id.currency_id",
        string="Currency",
    )
    wage_on_payroll = fields.Monetary(
        currency_field="currency_id",
        compute="_compute_wage_on_payroll",
    )
    employee_id = fields.Many2one(
        related="version_id.employee_id",
        readonly=True,
        required=True,
    )
    employee_type = fields.Selection(
        related="version_id.employee_type",
        string="Employee Type",
    )

    @api.depends("version_id")
    def _compute_wage_on_payroll(self) -> None:
        for line in self:
            line.wage_on_payroll = line.version_id._get_contract_wage()


class HrPayrollHeadcountWorkingRate(models.Model):
    _name = "hr.payroll.headcount.working.rate"
    _inherit = ["mixin.color"]
    _description = "Working Rate"

    rate = fields.Float()
    color = fields.Integer(default=lambda self: self._default_color())

    @api.depends("rate")
    def _compute_display_name(self):
        for working_rate in self:
            working_rate.display_name = self.env._(
                "%(rate)s Hours/week", rate=working_rate.rate
            )
