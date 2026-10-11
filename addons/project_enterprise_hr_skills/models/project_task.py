from odoo import fields, models
from odoo.fields import Domain

from odoo.addons.base.models.resource_utils import filter_domain_leaf


class ProjectTask(models.Model):
    _inherit = "project.task"

    def _get_additional_users(self, domain):
        users = super()._get_additional_users(domain)
        skill_search_domain = filter_domain_leaf(
            domain,
            lambda field: field == "user_skill_ids",
            field_name_mapping={"user_skill_ids": "name", "name": "dummy"},
        )
        if not skill_search_domain:
            return users
        skill_ids = self.env["hr.skill"]._search(skill_search_domain)
        employee_skill_model = self.env["hr.employee.skill"].sudo()
        user_skill_read_group = employee_skill_model._read_group(
            Domain("skill_id", "in", skill_ids)
            & employee_skill_model._domain_current(fields.Date.today()),
            [],
            ["employee_id:array_agg"],
        )
        matching_employee_ids = user_skill_read_group[0][0]
        return self.env["res.users"].search(
            [("employee_id", "in", matching_employee_ids)]
        )
