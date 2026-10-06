from odoo import fields, models
from odoo.fields import Domain


class ResCompany(models.Model):
    _inherit = "res.company"

    account_folder_id = fields.Many2one(
        comodel_name="document.document",
        string="Accounting Folder",
        compute="_compute_account_folder_id",
        precompute=True,
        store=True,
        readonly=False,
        domain=[("type", "=", "folder"), ("shortcut_document_id", "=", False)],
        check_company=True,
    )

    def _compute_account_folder_id(self) -> None:
        self.filtered(
            lambda c: not c.account_folder_id
        ).account_folder_id = self.env.ref(
            "document.document_finance_folder", raise_if_not_found=False
        )

    def _get_domain_used_folder_ids(self, folder_ids):
        return super()._get_domain_used_folder_ids(folder_ids) | Domain(
            "account_folder_id", "in", folder_ids
        )
