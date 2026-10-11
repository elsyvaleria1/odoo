from datetime import datetime, time

from dateutil.relativedelta import relativedelta

from odoo import fields, models
from odoo.libs.debug_log import DebugLog

from odoo.addons.hr_contract_salary.utils.hr_version import requires_hr_version_context

_debug = DebugLog(__name__)


class HrVersion(models.Model):
    _inherit = "hr.version"

    wage_with_holidays = fields.Monetary(
        classification="hr.compensation",
        groups="hr_payroll.group_hr_payroll_user",
    )
    wage_on_signature = fields.Monetary(
        classification="hr.compensation",
        groups="hr_payroll.group_hr_payroll_user",
    )
    final_yearly_costs = fields.Monetary(
        classification="hr.compensation",
        groups="hr_payroll.group_hr_payroll_user",
    )
    monthly_yearly_costs = fields.Monetary(
        classification="hr.compensation",
        groups="hr_payroll.group_hr_payroll_user",
    )
    salary_offer_ids = fields.One2many(groups="hr_payroll.group_hr_payroll_manager")

    @requires_hr_version_context()
    def _generate_salary_simulation_payslip(self):
        self.check_singleton()
        _debug.pipeline(
            "simulation_payslip",
            version=self,
            employee=self.employee_id,
            structure=self.structure_type_id.default_struct_id,
        )
        payslip = (
            self.env["hr.payslip"]
            .sudo()
            .create(
                {
                    "employee_id": self.employee_id.id,
                    "version_id": self.id,
                    "struct_id": self.structure_type_id.default_struct_id.id,
                    "company_id": self.employee_id.company_id.id,
                    "name": "Payslip Simulation",
                    "date_from": self.contract_date_start
                    + relativedelta(months=1, day=1),
                }
            )
        )

        if self.wage_type == "hourly":
            work_days_data = self.employee_id._get_work_duration_data_batch(
                datetime.combine(payslip.date_from, time.min),
                datetime.combine(payslip.date_to, time.max),
                compute_leaves=False,
                calendar=self.resource_calendar_id,
            )[self.employee_id.id]
            payslip.worked_days_line_ids = (
                self.env["hr.payslip.worked_days"]
                .sudo()
                .create(
                    {
                        "payslip_id": payslip.id,
                        "work_entry_type_id": self._get_default_work_entry_type_id(),
                        "number_of_days": work_days_data.get("days", 0),
                        "number_of_hours": work_days_data.get("hours", 0),
                    }
                )
            )

        old_wage_on_payroll = payslip.version_id.wage_on_signature
        old_wage = payslip.version_id.wage
        new_version_vals = {}
        part_time_schedules = {
            "90": (True, 2),
            "80": (False, 2),
            "60": (False, 4),
            "50": (False, 5),
            "40": (False, 6),
            "20": (False, 8),
        }
        if self.env.context.get("simulation_working_schedule"):
            working_schedule = str(
                self.env.context.get("simulation_working_schedule", "100")
            )
            if (
                working_schedule != "100"
                and working_schedule not in part_time_schedules
            ):
                _debug.logic(
                    "simulation_schedule_unmapped",
                    version=self,
                    value=working_schedule,
                )
                working_schedule = "100"
            old_calendar = payslip.version_id.company_id.resource_calendar_id
            new_calendar = self.env["resource.calendar"]
            if working_schedule in part_time_schedules:
                needs_two_weeks_calendar, remove_count = part_time_schedules[
                    working_schedule
                ]
                new_calendar = old_calendar.copy({"global_leave_ids": False})
                if new_calendar.two_weeks_calendar != needs_two_weeks_calendar:
                    new_calendar.action_switch_two_weeks()
                new_calendar.attendance_ids.filtered(lambda a: a.day_period != "lunch")[
                    :remove_count
                ].unlink()
            new_wage_on_payroll = old_wage_on_payroll * int(working_schedule) / 100.0
            new_wage = old_wage * int(working_schedule) / 100.0
            is_full_time = working_schedule == "100"
            new_version_vals.update(
                {
                    "resource_calendar_id": new_calendar.id,
                    "wage_on_signature": new_wage_on_payroll,
                    "wage": new_wage,
                }
            )

        else:
            is_full_time = True

        payslip = payslip.with_context(
            salary_simulation=True,
            salary_simulation_full_time=is_full_time,
            salary_simulation_full_time_wage_on_holidays=self.wage_with_holidays,
            salary_simulation_full_time_yearly_cost=self.final_yearly_costs,
            origin_version_id=self.env.context.get("origin_version_id", False),
            lang=None,
        )

        if not is_full_time:
            payslip.version_id.write(new_version_vals)

        payslip.compute_sheet()
        return payslip
