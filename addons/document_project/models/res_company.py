from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain


class ResCompany(models.Model):
    _inherit = "res.company"

    documents_project_folder_id = fields.Many2one(
        comodel_name="document.document",
        string="Project Folder",
        default=lambda self: self.env.ref(
            "document_project.document_project_folder", raise_if_not_found=False
        ),
        domain="[('type', '=', 'folder'), ('shortcut_document_id', '=', False)]",
        context=lambda env: {
            "default_type": "folder",
            "default_folder_id": (
                env.ref(
                    "document_project.document_project_folder", raise_if_not_found=False
                )
                or env["document.document"]
            ).id,
        },
        check_company=True,
    )

    @api.constrains("documents_project_folder_id")
    def _check_documents_project_folder_id_company_id(self) -> None:
        if wrong_companies := self.filtered(
            lambda c: c.documents_project_folder_id.company_id.id not in {False, c.id}
        ):
            companies_list = "\n- ".join(
                f"{company.name}: {company.documents_project_folder_id.name}"
                for company in wrong_companies
            )
            raise ValidationError(
                self.env._(
                    "Company Project Folders cannot be linked to another company.%s",
                    f"\n- {companies_list}",
                )
            )

    @api.model
    def _get_domain_used_folder_ids(self, folder_ids):
        return super()._get_domain_used_folder_ids(folder_ids) | Domain(
            "documents_project_folder_id", "in", folder_ids
        )
