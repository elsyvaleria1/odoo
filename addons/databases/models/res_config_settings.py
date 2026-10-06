from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # databases_apiuser is deprecated: Odoo.com supports /json/2 routes that only require an API key; will be removed in saas~19.2
    databases_apiuser = fields.Char(
        string="Odoo.com API User",
        config_parameter="databases.odoocom_apiuser",
        groups="base.group_system",
    )
    databases_apikey = fields.Char(
        string="Odoo.com API Key",
        classification="secret.credential",
        secret_parameter="databases.odoocom_apikey",
        groups="base.group_system",
    )
    databases_project_template_id = fields.Many2one(
        comodel_name="project.project",
        string="Project template",
        config_parameter="databases.odoocom_project_template",
        domain=[("is_template", "=", True)],
        groups="base.group_system",
    )
