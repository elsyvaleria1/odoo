from __future__ import annotations

from odoo import Command, models
from odoo.exceptions import UserError
from odoo.libs.filesystem import get_essential_mimetype, guess_mimetype

from odoo.addons.extract.tools.readers import PAGED


class AccountJournal(models.Model):
    _inherit = "account.journal"

    def _is_attachment_extractable(self, attachment) -> bool:
        if not attachment.raw:
            return False
        declared = get_essential_mimetype(attachment.mimetype or "")
        return guess_mimetype(attachment.raw, declared=declared) in PAGED

    def _get_bank_statements_available_import_formats(self):
        formats = super()._get_bank_statements_available_import_formats()
        formats.extend(["PDF", "JPEG", "PNG", "WEBP", "GIF", "BMP"])
        return formats

    def _import_bank_statement(self, attachments):
        extractable = attachments.filtered(self._is_attachment_extractable)
        if not extractable:
            return super()._import_bank_statement(attachments)
        if extractable != attachments:
            raise UserError(
                self.env._(
                    "Mixing scanned statements with other file types is not allowed."
                )
            )

        statements = self.env["account.bank.statement"].create(
            [
                {
                    "journal_id": self.id,
                    "attachment_ids": [Command.set(attachment.ids)],
                    "message_main_attachment_id": attachment.id,
                }
                for attachment in attachments
            ]
        )
        statements.action_extract_later()

        action = statements._get_records_action()
        if len(statements) > 1:
            action.update({"name": self.env._("Generated Bank Statements")})
        return action
