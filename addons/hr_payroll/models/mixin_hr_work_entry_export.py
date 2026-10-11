from base64 import b64encode
from calendar import monthrange
from datetime import datetime

from odoo import Command, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.tools import format_date


class MixinHrWorkEntryExport(models.AbstractModel):
    _name = "mixin.hr.work.entry.export"
    _description = "Work Entry Export Mixin"

    @api.model
    def _country_restriction(self):
        return False

    @api.model
    def default_get(self, fields):
        country_restriction = self._country_restriction()
        if country_restriction and country_restriction not in self.env.companies.mapped(
            "country_id.code"
        ):
            raise UserError(
                self.env._(
                    "You must be logged in a %(country_code)s company to use this feature",
                    country_code=country_restriction,
                )
            )
        return super().default_get(fields)

    def _get_domain_company(self):
        domain = Domain("id", "in", self.env.companies.ids)
        if restriction := self._country_restriction():
            domain &= Domain("partner_id.country_id.code", "=", restriction)
        return domain

    create_uid = fields.Many2one(
        comodel_name="res.users",
        index=True,
    )
    reference_year = fields.Integer(
        default=lambda self: fields.Date.today().year,
        required=True,
    )
    reference_month = fields.Selection(
        selection=[
            ("1", "January"),
            ("2", "February"),
            ("3", "March"),
            ("4", "April"),
            ("5", "May"),
            ("6", "June"),
            ("7", "July"),
            ("8", "August"),
            ("9", "September"),
            ("10", "October"),
            ("11", "November"),
            ("12", "December"),
        ],
        default=lambda self: str((fields.Date.today()).month),
        required=True,
    )
    eligible_employee_line_ids = fields.One2many(
        comodel_name="mixin.hr.work.entry.export.employee",
        inverse_name="export_id",
        string="Eligible Employees",
    )
    eligible_employee_count = fields.Integer(
        string="Eligible Employees Count",
        compute="_compute_eligible_employee_count",
    )
    period_start = fields.Date(
        compute="_compute_period_dates",
        store=True,
    )
    period_stop = fields.Date(
        compute="_compute_period_dates",
        store=True,
    )
    export_file = fields.Binary(readonly=True)
    export_filename = fields.Char(readonly=True)
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        required=True,
        domain=lambda self: self._get_domain_company(),
    )

    @api.depends("period_start")
    def _compute_display_name(self):
        for export in self:
            export.display_name = format_date(
                self.env,
                export.period_start,
                date_format="MMMM y",
                lang_code=self.env.user.lang,
            )

    @api.depends("reference_year", "reference_month")
    def _compute_period_dates(self) -> None:
        for export in self:
            export.period_start = datetime(
                export.reference_year, int(export.reference_month), 1
            ).date()
            export.period_stop = export.period_start.replace(
                day=monthrange(export.reference_year, int(export.reference_month))[1]
            )

    @api.depends("eligible_employee_line_ids")
    def _compute_eligible_employee_count(self) -> None:
        for export in self:
            export.eligible_employee_count = len(
                export.eligible_employee_line_ids.filtered(
                    lambda line: line.work_entry_ids and line.version_ids
                )
            )

    def _unlink_empty_eligible_employee_lines(self) -> None:
        self.eligible_employee_line_ids.filtered(
            lambda line: not line.work_entry_ids or not line.version_ids
        ).unlink()

    @api.model
    def _get_authorized_employee_types(self) -> list:
        return ["employee", "worker"]

    def _get_employee_ids(self):
        return self.env["hr.employee"]._search(
            domain=[
                ("company_id", "=", self.company_id.id),
                ("employee_type", "in", self._get_authorized_employee_types()),
            ],
        )

    def _get_relevant_work_entries_by_employee(self, employee_ids=None):
        if employee_ids is None:
            employee_ids = self._get_employee_ids()
        return dict(
            self.env["hr.work.entry"]._read_group(
                domain=[
                    ("employee_id", "in", employee_ids),
                    ("date", "<=", self.period_stop),
                    ("date", ">=", self.period_start),
                    ("state", "in", ["draft", "validated", "conflict"]),
                ],
                groupby=["employee_id"],
                aggregates=["id:recordset"],
            )
        )

    def _get_contracts_by_employee(self, employee_ids=None):
        if employee_ids is None:
            employee_ids = self._get_employee_ids()
        return dict(
            self.env["hr.version"]._read_group(
                domain=[
                    ("employee_id", "in", employee_ids),
                    ("contract_date_start", "!=", False),
                    ("contract_date_start", "<=", self.period_stop),
                    "|",
                    ("contract_date_end", ">=", self.period_start),
                    ("contract_date_end", "=", False),
                ],
                groupby=["employee_id"],
                aggregates=["id:recordset"],
            )
        )

    def _generate_export_file(self):
        raise NotImplementedError

    def _generate_export_filename(self):
        raise NotImplementedError

    def _get_name(self) -> str:
        return self.env._("Work Entries Export")

    def _get_view_ref(self) -> str:
        return "hr_payroll.hr_work_entry_export_mixin_form_view"

    def action_export_file(self) -> dict:
        self.check_singleton()
        self.eligible_employee_line_ids._check_data()
        self.eligible_employee_line_ids._check_work_entries()
        self.export_file = b64encode(self._generate_export_file().encode())
        self.export_filename = self._generate_export_filename()
        return {
            "name": self._get_name(),
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "views": [(self.env.ref(self._get_view_ref()).id, "form")],
        }

    def action_populate(self) -> dict | None:
        self.check_singleton()
        contracts_by_employee = self._get_contracts_by_employee()
        relevant_work_entries_by_employee = (
            self._get_relevant_work_entries_by_employee()
        )
        lines = [Command.clear()]
        for employee, contracts in contracts_by_employee.items():
            if relevant_work_entries_by_employee.get(employee):
                lines.append(
                    (
                        0,
                        0,
                        {
                            "export_id": self.id,
                            "employee_id": employee.id,
                            "version_ids": [Command.set(contracts.ids)],
                        },
                    )
                )
        self.eligible_employee_line_ids = lines
        return {
            "name": self._get_name(),
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "views": [(self.env.ref(self._get_view_ref()).id, "form")],
        }

    def action_view_employees(self) -> dict:
        self.check_singleton()
        return {
            "name": self.env._("Eligible Employees"),
            "res_model": self.eligible_employee_line_ids._name,
            "domain": [("id", "in", self.eligible_employee_line_ids.ids)],
            "context": {"default_export_id": self.id},
            "type": "ir.actions.act_window",
            "view_mode": "list",
        }
