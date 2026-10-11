from odoo import models
from odoo.exceptions import UserError


class AccountJournal(models.Model):
    _inherit = "account.journal"

    def _get_bank_statements_available_import_formats(self):
        rslt = super()._get_bank_statements_available_import_formats()
        rslt.extend(["CSV", "XLS", "XLSX"])
        return rslt

    def _is_spreadsheet_file(self, filename) -> bool:
        return bool(filename) and filename.lower().strip().endswith(
            (".csv", ".xls", ".xlsx")
        )

    def _import_bank_statement(self, attachments):
        if len(attachments) > 1:
            csv = [self._is_spreadsheet_file(att.name) for att in attachments]
            if True in csv and False in csv:
                raise UserError(
                    self.env._("Mixing CSV files with other file types is not allowed.")
                )
            if csv.count(True) > 1:
                raise UserError(self.env._("Only one CSV file can be selected."))
            return super()._import_bank_statement(attachments)

        if not self._is_spreadsheet_file(attachments.name):
            return super()._import_bank_statement(attachments)
        ctx = dict(self.env.context)
        import_wizard = self.env["base_import.import"].create(
            {
                "res_model": "account.bank.statement.line",
                "file": attachments.raw,
                "file_name": attachments.name,
                "file_type": attachments.mimetype,
            }
        )
        ctx["wizard_id"] = import_wizard.id
        ctx["default_journal_id"] = self.id
        ctx["attachment_ids"] = attachments.ids
        return {
            "type": "ir.actions.client",
            "tag": "import_bank_stmt",
            "params": {
                "model": "account.bank.statement.line",
                "context": ctx,
                "filename": attachments.name,
            },
        }
