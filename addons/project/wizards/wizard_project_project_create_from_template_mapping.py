from odoo import fields, models


class WizardProjectProjectCreateFromTemplateMapping(models.TransientModel):
    _name = "wizard.project.project.create.from.template.mapping"
    _description = "Project role to users mapping"

    wizard_id = fields.Many2one(
        comodel_name="wizard.project.project.create.from.template",
        export_string_translation=False,
    )
    role_id = fields.Many2one(
        comodel_name="resource.role",
        string="Project Role",
        required=True,
    )
    user_ids = fields.Many2many(
        comodel_name="res.users",
        relation="project_template_role_to_users_map_res_users_rel",
        string="Assignees",
        domain=[("share", "=", False), ("active", "=", True)],
    )
