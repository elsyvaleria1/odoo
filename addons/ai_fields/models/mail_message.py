from odoo import models


class MailMessage(models.Model):
    _inherit = "mail.message"

    def _ai_read(self, fnames, files_dict) -> tuple:
        """Send the subject, body, author_id and date of the comments to the LLM when no field
        is specified, ignoring the messages of the other types and subtypes.
        """
        if fnames:
            return super()._ai_read(fnames, files_dict)
        msg_subtype = self.env.ref("mail.mt_comment")
        msg_types = ("comment", "email", "email_outgoing")
        return super(
            MailMessage,
            self.filtered(
                lambda m: m.message_type in msg_types and m.subtype_id == msg_subtype
            ),
        )._ai_read(["subject", "body", "author_id", "date"], files_dict)
