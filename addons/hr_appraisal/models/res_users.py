from odoo import models


class ResUsers(models.Model):
    _inherit = "res.users"

    def get_employee_autocomplete_ids(self):
        self.check_singleton()
        Employee = self.env["hr.employee"]
        if self.has_group("hr_appraisal.group_hr_appraisal_user"):
            return Employee.search([("company_id", "in", self.env.companies.ids)])
        user_employees = Employee.search([("user_id", "=", self.id)])
        children = Employee
        if user_employees:
            Employee.flush_model(["parent_id"])
            children = Employee.search(
                [
                    ("id", "child_of", user_employees.ids),
                    ("company_id", "in", self.env.companies.ids),
                ]
            )
        return children | self.employee_ids
