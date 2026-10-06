from odoo import api, fields, models
from odoo.fields import Domain


class ResCompany(models.Model):
    _inherit = "res.company"

    peppol_reception_mode = fields.Selection(
        selection=[
            ("journal", "Receive as Bills"),
            ("documents", "Receive as Documents"),
        ],
        default="journal",
    )
    documents_account_peppol_folder_id = fields.Many2one(
        comodel_name="document.document",
        string="Document Folder",
        domain=[("type", "=", "folder"), ("shortcut_document_id", "=", False)],
        check_company=True,
    )
    documents_account_peppol_tag_ids = fields.Many2many(
        comodel_name="document.tag",
        string="Document Tags",
    )

    @api.model
    def _get_domain_used_folder_ids(self, folder_ids):
        return super()._get_domain_used_folder_ids(folder_ids) | Domain(
            "documents_account_peppol_folder_id", "in", folder_ids
        )
