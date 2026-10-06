from odoo import api, fields, models
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog

from odoo.addons.resource.models.utils import filter_domain_leaf

_debug = DebugLog(__name__)


class PlanningSlot(models.Model):
    _inherit = "planning.slot"

    employee_skill_ids = fields.One2many(
        related="employee_id.current_employee_skill_ids",
        string="Skills",
    )

    @api.model
    def _group_expand_resource_id(self, resources, domain):
        """
        overriding
        _group_expand_resource_id adds 'resource_ids' in the domain corresponding to 'employee_skill_ids' fields already in the domain
        """
        domain = Domain(domain)
        # 1. Transform the current domain to search hr.skill records
        skill_search_domain = filter_domain_leaf(
            domain,
            lambda field: field == "employee_skill_ids",
            field_name_mapping={"employee_skill_ids": "name"},
        )
        if not skill_search_domain:
            _debug.logic(
                "planning_skill_expand_passthrough",
                reason="no_skill_leaf",
                resources=resources,
            )
            return super()._group_expand_resource_id(resources, domain)

        # 2. Get matching employee_ids for every employee_skill_id found in the initial domain
        skill_ids = self.env["hr.skill"]._search(skill_search_domain)
        employee_skill_model = self.env["hr.employee.skill"]
        employee_skill_read_group = employee_skill_model._read_group(
            Domain("skill_id", "in", skill_ids)
            & employee_skill_model._domain_current(fields.Date.today()),
            [],
            ["employee_id:array_agg"],
        )
        matching_employee_ids = employee_skill_read_group[0][0]

        # 3. Looking for corresponding resources
        matching_resource_ids = self.env["resource.resource"]._search(
            [("employee_id", "in", matching_employee_ids)]
        )

        filtered_domain = Domain("resource_id", "in", matching_resource_ids) & domain
        _debug.pipeline(
            "planning_skill_expand_filtered",
            resources=resources,
            skills=len(skill_ids),
            matching_employees=len(matching_employee_ids),
            matching_resources=len(matching_resource_ids),
        )
        return super()._group_expand_resource_id(resources, filtered_domain)
