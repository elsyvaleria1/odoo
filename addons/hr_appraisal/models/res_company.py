import datetime

from dateutil.relativedelta import relativedelta

from odoo import Command, api, fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    def _get_default_appraisal_confirm_mail_template(self):
        return self.env.ref(
            "hr_appraisal.mail_template_appraisal_confirm", raise_if_not_found=False
        )

    appraisal_plan = fields.Boolean(
        string="Automatically Generate Appraisals",
        default=True,
    )
    assessment_note_ids = fields.One2many(
        comodel_name="hr.appraisal.note",
        inverse_name="company_id",
    )
    appraisal_confirm_mail_template = fields.Many2one(
        comodel_name="mail.template",
        default=lambda self: self._get_default_appraisal_confirm_mail_template(),
        domain="[('model', '=', 'hr.appraisal')]",
    )
    duration_after_recruitment = fields.Integer(
        string="Create an Appraisal after recruitment",
        default=6,
    )
    duration_first_appraisal = fields.Integer(
        string="Create a first Appraisal after",
        default=6,
    )
    duration_next_appraisal = fields.Integer(
        string="Create a second Appraisal after",
        default=12,
    )

    _positif_number_months = models.Constraint(
        "CHECK(duration_after_recruitment > 0 AND duration_first_appraisal > 0 AND duration_next_appraisal > 0)",
        "The duration time must be bigger or equal to 1 month.",
    )

    @api.model
    def _prepare_default_assessment_note_commands(self) -> list:
        return [
            Command.create({"name": self.env._("Needs improvement"), "sequence": 1}),
            Command.create({"name": self.env._("Meets expectations"), "sequence": 2}),
            Command.create({"name": self.env._("Exceeds expectations"), "sequence": 3}),
            Command.create(
                {"name": self.env._("Strongly Exceed Expectations"), "sequence": 4}
            ),
        ]

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        for company, vals in zip(res, vals_list, strict=True):
            if not vals.get("assessment_note_ids"):
                company.sudo().write(
                    {
                        "assessment_note_ids": self._prepare_default_assessment_note_commands(),
                    }
                )
        return res

    def _create_new_appraisal(self, employees):
        days = int(
            self.env.registry.settings.get(
                self.env, "hr_appraisal.appraisal_create_in_advance_days", 8
            )
        )
        appraisal_values = [
            {
                "department_id": employee.department_id.id,
                "employee_id": employee.id,
                "date_close": employee.next_appraisal_date + relativedelta(days=days),
                "manager_ids": employee.parent_id,
                "state": "2_pending",
                "employee_feedback_published": False,
                "manager_feedback_published": False,
            }
            for employee in employees
        ]
        return self.env["hr.appraisal"].create(appraisal_values)

    def _run_employee_appraisal_plans(self) -> None:
        companies = self.env["res.company"].search([("appraisal_plan", "=", True)])
        current_date = datetime.date.today()
        all_employees = self.env["hr.employee"].search(
            [
                ("next_appraisal_date", "<=", current_date),
                ("company_id", "in", companies.ids),
            ]
        )
        if all_employees:
            appraisals = self._create_new_appraisal(all_employees)
            for appraisal in appraisals:
                appraisal.employee_id.sudo().write(
                    {
                        "last_appraisal_id": appraisal.id,
                    }
                )
            appraisals._generate_activities()
