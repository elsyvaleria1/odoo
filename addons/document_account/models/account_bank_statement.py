from odoo import models


class AccountBankStatement(models.Model):
    _name = "account.bank.statement"
    _inherit = ["account.bank.statement", "mixin.documents"]

    def _get_document_folder(self) -> models.Model:
        return (
            self.env["document.account.folder.setting"]
            .with_privilege(
                "document_account.privilege_read_folder_setting",
                reason="a statement's PDF files into its journal's folder",
            )
            .search([("journal_id", "=", self.journal_id.id)], limit=1)
            .folder_id.with_env(self.env)
        )

    def _get_document_owner(self) -> models.Model:
        return self.env.user

    def _prepare_document_vals(self, attachment: models.Model) -> dict:
        if attachment.mimetype != "application/pdf":
            return {}
        vals = super()._prepare_document_vals(attachment)
        if not vals:
            return vals
        vals["company_id"] = vals["company_id"] or self.company_id.id
        if file_name := self._get_document_file_name():
            vals |= {"name": file_name, "attachment_name": file_name}
        return vals

    def _get_document_file_name(self) -> str | None:
        self.check_singleton()
        if not self.name:
            return None
        return f"{self.name} {self._get_document_account_label()}.pdf"

    def _get_document_account_label(self) -> str:
        self.check_singleton()
        return self.journal_id.with_context(lang=self.company_id.partner_id.lang).name

    def action_generate_attachment(self):
        return super(
            AccountBankStatement, self.with_context(no_document=True)
        ).action_generate_attachment()
