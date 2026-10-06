from odoo import api, fields, models


class HrDepartment(models.Model):
    _inherit = "hr.department"

    appraisals_to_process_count = fields.Integer(
        string="Appraisals to Process",
        compute="_compute_appraisals_to_process",
    )
    appraisal_template_ids = fields.Many2many(
        comodel_name="hr.appraisal.template",
        relation="hr_appraisal_template_hr_department_rel",
        column1="hr_department_id",
        string="Appraisal Templates",
    )
    appraisal_properties_definition = fields.PropertiesDefinition(
        string="Appraisal Properties"
    )

    @api.depends("member_ids.appraisal_ids.state")
    def _compute_appraisals_to_process(self) -> None:
        appraisals = self.env["hr.appraisal"]._read_group(
            [
                ("department_id", "in", self.ids),
                ("state", "in", ["1_new", "2_pending"]),
            ],
            ["department_id"],
            ["__count"],
        )
        result = {department.id: count for department, count in appraisals}
        for department in self:
            department.appraisals_to_process_count = result.get(department.id, 0)

    def action_view_appraisals(self):
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "hr_appraisal.open_view_hr_appraisal_graph_department"
        )
        action["context"] = {
            **self.env["ir.actions.actions"]._eval_action_context(action["context"]),
            "search_default_department_id": self.id,
        }
        return action
