from collections import defaultdict
from datetime import date
from typing import TYPE_CHECKING

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.tools import float_compare

from odoo.addons.hr_contract_salary.utils.hr_version import (
    hr_version_context,
    requires_hr_version_context,
)

if TYPE_CHECKING:
    from odoo.addons.hr.models.hr_version import HrVersion


class HrContractSalaryOffer(models.Model):
    _inherit = "hr.contract.salary.offer"

    def _get_default_struct_id(self):
        return (
            self.env["hr.version"]
            ._get_default_structure_type(self.env.company.country_id.id)
            .default_struct_id
        )

    def _get_default_resource_calendar_id(self):
        return self.env.company.resource_calendar_id

    is_simulation_offer = fields.Boolean()
    monthly_wage = fields.Monetary(
        compute="_compute_monthly_wage",
        inverse="_inverse_monthly_wage",
        store=True,
        readonly=False,
    )
    final_yearly_costs = fields.Monetary(
        readonly=False,
    )
    budget_type = fields.Selection(
        selection=[
            ("monthly_gross", "Gross Per Month"),
            ("yearly_employer", "Yearly Employer Cost"),
        ],
        default="yearly_employer",
        required=True,
    )
    country_id = fields.Many2one(related="company_id.country_id")
    structure_id = fields.Many2one(
        comodel_name="hr.payroll.structure",
        string="Salary Structure",
        default=lambda self: self._get_default_struct_id(),
        domain="[('country_id', 'in', (country_id, False))]",
    )
    resource_calendar_id = fields.Many2one(
        comodel_name="resource.calendar",
        string="Working Schedule",
        default=lambda self: self._get_default_resource_calendar_id(),
        check_company=True,
    )
    simulation_employee_id = fields.Many2one(
        comodel_name="hr.employee",
        domain=[("contract_date_start", "!=", False)],
        check_company=True,
    )
    gross_wage = fields.Monetary(
        compute="_compute_salary",
        store=True,
    )
    net_wage = fields.Monetary(
        compute="_compute_salary",
        store=True,
    )
    monthly_benefits = fields.Monetary(
        compute="_compute_salary",
        store=True,
    )
    yearly_benefits = fields.Monetary(
        compute="_compute_salary",
        store=True,
    )
    yearly_employer_cost = fields.Monetary(
        compute="_compute_salary",
        store=True,
    )
    monthly_employer_cost = fields.Monetary(
        compute="_compute_salary",
        store=True,
    )
    is_full_time = fields.Boolean(
        compute="_compute_salary",
        store=True,
    )

    @requires_hr_version_context()
    def _acquire_version(self, *, apply_offer_wage: bool = True) -> HrVersion:
        self.check_singleton()
        version = super()._acquire_version()
        version_vals = {}
        if self.is_simulation_offer:
            if self.simulation_employee_id:
                version = self.simulation_employee_id.version_id
            version_vals.update(
                {
                    "structure_type_id": self.structure_id.type_id.id,
                }
            )
        calendar = version.resource_calendar_id
        if calendar == self.env["resource.calendar"]._get_fully_flexible_calendar():
            calendar = (
                self.resource_calendar_id
                or self.company_id.resource_calendar_id
                or self._get_default_resource_calendar_id()
                or calendar
            )
        version_vals["resource_calendar_id"] = calendar.id
        if apply_offer_wage:
            version_vals.update(
                {
                    version._get_contract_wage_field_name(): self.monthly_wage,
                    "wage_with_holidays": self.monthly_wage,
                }
            )
        if not version.contract_date_start:
            current_version = self.employee_id.current_version_id
            if current_version.contract_date_start:
                current_version.write(
                    {"contract_date_end": version.date_version - relativedelta(days=1)}
                )
            version_vals.update({"contract_date_start": version.date_version})
        version.write(version_vals)
        version._inverse_wage_with_holidays()
        return version

    @api.onchange("simulation_employee_id")
    def _onchange_simulation_employee_id(self) -> None:
        if self.simulation_employee_id:
            version = self.simulation_employee_id.current_version_id
            self.monthly_wage = version._get_contract_wage()
            self.resource_calendar_id = version.resource_calendar_id
            self.structure_id = version.structure_type_id.default_struct_id

    @api.depends("final_yearly_costs")
    def _compute_monthly_wage(self) -> None:
        monthly_wage_by_offer = {}
        with hr_version_context(self) as offers:
            for offer in offers:
                version = offer._acquire_version(apply_offer_wage=False)
                monthly_wage_by_offer[offer] = version._get_gross_from_employer_costs(
                    offer.final_yearly_costs
                )
        for offer in self:
            offer.monthly_wage = monthly_wage_by_offer[offer]

    def _inverse_monthly_wage(self) -> None:
        final_yearly_costs_by_offer = {}
        with hr_version_context(self.sudo()) as offers:
            for offer in offers:
                version = offer._acquire_version()
                final_yearly_costs_by_offer[offer] = (
                    version._get_employer_costs_from_gross(offer.monthly_wage)
                )
        for offer in self:
            offer.final_yearly_costs = final_yearly_costs_by_offer[offer]

    @api.depends("monthly_wage", "structure_id", "resource_calendar_id")
    def _compute_salary(self) -> None:
        vals_by_offer = {}
        with hr_version_context(self) as offers:
            for offer in offers:
                version = offer._acquire_version()
                payslip = version._generate_salary_simulation_payslip()
                yearly_employer_cost = version._get_employer_costs_from_gross(
                    version._get_contract_wage()
                )
                monthly_benefits, yearly_benefits = offer._get_benefits(version)
                vals_by_offer[offer] = {
                    "is_full_time": float_compare(version.work_time_rate, 1.0, 4) == 0,
                    "gross_wage": payslip._get_line_values(["BASIC"])["BASIC"][
                        payslip.id
                    ]["total"],
                    "net_wage": payslip._get_line_values(["NET"])["NET"][payslip.id][
                        "total"
                    ],
                    "monthly_benefits": monthly_benefits,
                    "yearly_benefits": yearly_benefits,
                    "yearly_employer_cost": yearly_employer_cost,
                    "monthly_employer_cost": round(yearly_employer_cost / 12, 2),
                }

        for offer in self:
            offer.update(vals_by_offer[offer])

    def _get_benefits(self, version) -> tuple:
        monthly_benefit_category = self.env.ref(
            "hr_contract_salary.hr_contract_salary_resume_category_monthly_benefits"
        )
        yearly_benefit_category = self.env.ref(
            "hr_contract_salary.hr_contract_salary_resume_category_yearly_benefits"
        )
        resume_lines = (
            self.env["hr.contract.salary.resume"]
            .sudo()
            .with_company(version.company_id)
            .search(
                [
                    "|",
                    ("structure_type_id", "=", False),
                    ("structure_type_id", "=", version.structure_type_id.id),
                    ("value_type", "=", "sum"),
                    (
                        "category_id",
                        "in",
                        (monthly_benefit_category.id, yearly_benefit_category.id),
                    ),
                ]
            )
        )
        result = defaultdict(int)
        for resume_line in resume_lines:
            value = 0
            for benefit in resume_line.benefit_ids:
                if not benefit.fold_field or version[benefit.fold_field]:
                    field = benefit.field
                    value += (
                        version[field]
                        if benefit.source == "field"
                        else version._get_property_input_value(
                            benefit.salary_rule_id.code
                        )
                    )
            result[resume_line.category_id.id] += round(float(value), 2)
        return result[monthly_benefit_category.id], result[yearly_benefit_category.id]

    @api.model
    def action_cron_remove_simulation_offers(self):
        older_than_one_month_offers = self.env["hr.contract.salary.offer"].search(
            [
                ("is_simulation_offer", "=", True),
                ("create_date", "<", date.today() - relativedelta(months=1)),
            ]
        )
        return older_than_one_month_offers.unlink()

    def action_view_salary_configurator(self) -> dict:
        self.check_singleton()
        self.resource_calendar_id = (
            self.resource_calendar_id or self._get_default_resource_calendar_id()
        )
        return {
            "type": "ir.actions.act_url",
            "url": self.url,
            "target": "new",
        }
