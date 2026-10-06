from odoo import models


class AccountBankStatement(models.Model):
    _name = "account.bank.statement"
    _inherit = ["account.bank.statement", "mixin.documents"]

    def _get_document_folder(self) -> models.Model:
        # the journal alone names the setting: a setting made by hand may carry
        # the active company instead of its journal's
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
        # the statement the bank issues is the PDF; the .txt or .xlsx a
        # statement is imported from stays on the record only
        if attachment.mimetype != "application/pdf":
            return {}
        vals = super()._prepare_document_vals(attachment)
        if not vals:
            return vals
        # a folder shared by every company carries none: the statement's names it
        vals["company_id"] = vals["company_id"] or self.company_id.id
        if file_name := self._get_document_file_name():
            # attachment_name is related to the attachment: document.create
            # renames the file itself, so the chatter shows the same name
            vals |= {"name": file_name, "attachment_name": file_name}
        return vals

    def _get_document_file_name(self) -> str | None:
        """Name a statement's PDF ``<statement name> <account label>.pdf``.

        :return: the file name, or None when the statement has no name yet
        :rtype: str | None
        """
        self.check_singleton()
        if not self.name:
            return None
        # one folder holds every account, so the period alone is ambiguous
        return f"{self.name} {self._get_document_account_label()}.pdf"

    def _get_document_account_label(self) -> str:
        self.check_singleton()
        # the journal name is translated; reading it in the company's language
        # keeps the file name from depending on who attached the PDF
        return self.journal_id.with_context(lang=self.company_id.partner_id.lang).name

    def action_generate_attachment(self):
        # the report Odoo prints from the statement is not the one the bank
        # issued, so it stays on the record
        return super(
            AccountBankStatement, self.with_context(no_document=True)
        ).action_generate_attachment()
