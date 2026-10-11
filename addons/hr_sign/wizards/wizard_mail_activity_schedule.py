from odoo import Command, models


class WizardMailActivitySchedule(models.TransientModel):
    _inherit = "wizard.mail.activity.schedule"

    def _plan_filtered_activity_templates_to_schedule(self):
        if self.res_model != "hr.employee":
            return super()._plan_filtered_activity_templates_to_schedule()
        return self.plan_id.template_ids.filtered(
            lambda a: not a.is_signature_request or a.responsible_count > 2
        )

    def action_schedule_plan(self):
        res = super().action_schedule_plan()
        if self.res_model != "hr.employee":
            return res

        for employee in self._get_applied_on_records():
            for signature_request in (
                self.plan_id.template_ids
                - self._plan_filtered_activity_templates_to_schedule()
            ):
                employee_role = signature_request.employee_role_id
                responsible = signature_request._get_responsible_and_complaints(
                    self.plan_on_demand_user_id, employee
                )["responsible"]

                self.env["wizard.hr.employee.send.sign.request"].sudo().create(
                    {
                        "version_id": employee.version_id.id,
                        "employee_ids": [Command.link(employee.id)],
                        "responsible_id": responsible.id,
                        "employee_role_id": employee_role and employee_role.id,
                        "sign_template_ids": [
                            Command.link(signature_request.sign_template_id.id)
                        ],
                        "subject": self.env._("Signature Request"),
                    }
                ).with_env(self.env).action_confirm_signature()

        return res
