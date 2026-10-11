from odoo import models


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    def _to_store(self, store, field_specs, **kwargs) -> None:
        if not self.env.user._is_portal() or "access_token" in field_specs:
            super()._to_store(store, field_specs, **kwargs)
            return

        article_thread_ids = set(
            self.env["knowledge.article.thread"]
            .sudo(False)
            .with_user(self.env.user)
            .browse(
                self.filtered(
                    lambda attachment: (
                        attachment.res_model == "knowledge.article.thread"
                    )
                ).mapped("res_id")
            )
            .filtered(lambda thread: thread.has_access("read"))
            .ids
        )
        attachments_with_token = self.filtered(
            lambda attachment: (
                attachment.res_model == "knowledge.article.thread"
                and attachment.res_id in article_thread_ids
            )
        )
        super(IrAttachment, self - attachments_with_token)._to_store(
            store, field_specs, **kwargs
        )
        field_specs = [
            *field_specs,
            *store._format_fields(attachments_with_token, ["access_token"]),
        ]
        super(IrAttachment, attachments_with_token)._to_store(
            store, field_specs, **kwargs
        )
