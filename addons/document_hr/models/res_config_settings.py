from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    documents_hr_settings = fields.Boolean(
        related="company_id.documents_hr_settings",
        string="Human Resources",
        readonly=False,
    )
    documents_employee_folder_id = fields.Many2one(
        comodel_name="document.document",
        related="company_id.documents_employee_folder_id",
        readonly=False,
        domain=[("type", "=", "folder"), ("shortcut_document_id", "=", False)],
    )
    employee_subfolders = fields.Char(
        related="company_id.employee_subfolders",
        string="Employees Subfolder",
        readonly=False,
        help="Comma separated string of folder names that need to be created under each employee folder.",
    )
    documents_hr_contracts_tags = fields.Many2many(
        comodel_name="document.tag",
        related="company_id.documents_hr_contracts_tags",
        string="Contracts",
        readonly=False,
    )
