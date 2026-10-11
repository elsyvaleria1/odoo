from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardMailActivitySchedule(models.TransientModel):
    _inherit = "wizard.mail.activity.schedule"

    department_id = fields.Many2one(
        comodel_name="hr.department",
        compute="_compute_department_id",
    )
    plan_department_filterable = fields.Boolean(
        compute="_compute_plan_department_filterable"
    )

    @api.depends("company_id", "res_model", "department_id")
    def _compute_plan_available_ids(self) -> None:
        todo = self.filtered(lambda s: s.plan_department_filterable)
        for scheduler in todo:
            domain = scheduler._get_domain_plan_available_base()
            if not scheduler.department_id:
                domain &= Domain("department_id", "=", False)
            else:
                domain &= Domain("department_id", "=", False) | Domain(
                    "department_id", "=", scheduler.department_id.id
                )
            scheduler.plan_available_ids = self.env["mail.activity.plan"].search(domain)  # noqa: E8507 -- a transient wizard: one record
            _debug.logic(
                "plans_available",
                schedule=scheduler.id,
                department=scheduler.department_id.id,
                plans=len(scheduler.plan_available_ids),
            )
        super(WizardMailActivitySchedule, self - todo)._compute_plan_available_ids()

    @api.depends("res_model")
    def _compute_plan_department_filterable(self) -> None:
        Plan = self.env["mail.activity.plan"]
        for wizard in self:
            wizard.plan_department_filterable = Plan._is_department_assignable(
                wizard.res_model
            )

    @api.depends("res_model_id", "res_ids")
    def _compute_department_id(self) -> None:
        for wizard in self:
            if wizard.plan_department_filterable:
                applied_on = wizard._get_applied_on_records()
                all_departments = applied_on.department_id
                wizard.department_id = (
                    False if len(all_departments) > 1 else all_departments
                )
                _debug.logic(
                    "department_from_records",
                    schedule=wizard.id,
                    records=applied_on,
                    departments=all_departments,
                    department=wizard.department_id.id,
                )
            else:
                wizard.department_id = False

    @api.depends("res_model", "res_ids")
    def _compute_plan_date(self) -> None:
        handled = self.env["wizard.mail.activity.schedule"]
        for scheduler in self.filtered(lambda s: s.res_model == "hr.employee"):
            selected_employees = scheduler._get_applied_on_records()
            start_dates = selected_employees.filtered("date_start").mapped("date_start")
            if not start_dates:
                continue
            today = scheduler._launcher_today()
            planned_due_date = min(start_dates)
            if planned_due_date < today or (planned_due_date - today).days < 30:
                scheduler.plan_date = today + relativedelta(days=+30)
            else:
                scheduler.plan_date = planned_due_date
            _debug.logic(
                "plan_date_computed",
                schedule=scheduler.id,
                earliest_start=planned_due_date,
                employees=len(start_dates),
                plan_date=scheduler.plan_date,
            )
            handled |= scheduler
        super(WizardMailActivitySchedule, self - handled)._compute_plan_date()
