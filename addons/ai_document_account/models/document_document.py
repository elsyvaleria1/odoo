from odoo import api, fields, models


class DocumentsDocument(models.Model):
    _inherit = "document.document"

    ai_document_or_env_company_id = fields.Many2one(
        comodel_name="res.company",
        string="AI Company",
        compute="_compute_ai_document_or_env_company_id",
    )

    @api.depends("company_id")
    def _compute_ai_document_or_env_company_id(self) -> None:
        for document in self:
            document.ai_document_or_env_company_id = (
                document.company_id or self.env.company
            )
