from odoo import Command, api, models
from odoo.api import ValuesType


class ResCompany(models.Model):
    _inherit = "res.company"

    def _prepare_field_service_project_vals_list(self) -> list[ValuesType]:
        project_name = self.env._("Field Service")
        step_data = (
            self.env["ir.model.data"]
            .sudo()
            .search_read(
                [
                    ("module", "=", "industry_fsm"),
                    ("name", "like", "planning_project_stage_"),
                ],
                ["res_id"],
            )
        )
        workflow_step_ids = [Command.link(row["res_id"]) for row in step_data]
        return [
            {
                "name": project_name,
                "is_fsm": True,
                "allow_timesheets": True,
                "workflow_step_ids": workflow_step_ids,
                "company_id": company.id,
            }
            for company in self
        ]

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        self.env["project.project"].sudo().create(
            companies._prepare_field_service_project_vals_list()
        )
        return companies
