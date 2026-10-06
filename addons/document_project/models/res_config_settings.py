from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    documents_project_folder_id = fields.Many2one(
        comodel_name="document.document",
        related="company_id.documents_project_folder_id",
        string="Project Folder",
        readonly=False,
        domain="[('type', '=', 'folder'), ('shortcut_document_id', '=', False)]",
        check_company=True,
    )
