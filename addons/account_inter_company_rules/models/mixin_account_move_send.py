import logging

from odoo import models

_logger = logging.getLogger(__name__)


class MixinAccountMoveSend(models.AbstractModel):
    _inherit = "mixin.account.move.send"

    def _generate_and_send_invoices(
        self,
        moves,
        from_cron=False,
        allow_raising=True,
        allow_fallback_pdf=False,
        **custom_settings,
    ):
        # EXTENDS 'account' - to create the pdf attachment
        # in the matching inter-company move
        res = super()._generate_and_send_invoices(
            moves,
            from_cron=from_cron,
            allow_raising=allow_raising,
            allow_fallback_pdf=allow_fallback_pdf,
            **custom_settings,
        )

        # auto_generated + auto_invoice_id already identifies a generated
        # mirror exactly, so no prefilter on the source moves is needed beyond
        # "does it have a PDF to copy". The previous one read every res.company
        # and all their partner ids on every send, and matched company partners
        # by commercial_partner_id while generation matches them with
        # `parent_of`: for a contact under an is_company child of a company
        # partner the two disagree, a bill *is* generated, and this lookup could
        # never find it — so that bill silently never received its PDF.
        # It also passed include_receipts=True on both sides while the
        # generation trigger excludes receipts; the two halves now agree.
        moves_with_attachments = moves.filtered("message_main_attachment_id")

        ico_moves = (
            self.env["account.move"]
            .sudo()
            .search(
                [
                    ("auto_generated", "=", True),
                    ("auto_invoice_id", "in", moves_with_attachments.ids),
                ]
            )
        )

        existing_attachments_by_key = {}
        for attachment in (
            self.env["ir.attachment"]
            .sudo()
            .search(
                [
                    ("res_model", "=", "account.move"),
                    ("res_id", "in", ico_moves.ids),
                ]
            )
        ):
            existing_attachments_by_key.setdefault(
                (attachment.res_id, attachment.name), attachment
            )

        for ico_move in ico_moves:
            original_move = ico_move.auto_invoice_id
            move_attachment = original_move.message_main_attachment_id
            if not move_attachment:  # shouldn't happen but just in case
                continue

            attachment_name = f"{original_move.name}.pdf"
            existing = existing_attachments_by_key.get((ico_move.id, attachment_name))
            if existing:
                # Re-sending the source invoice, or a from_cron retry, must not
                # stack another identical PDF on the bill and orphan this one.
                ico_move.message_main_attachment_id = existing
                continue

            if not ico_move.company_id.intercompany_user_id:
                # with_user(False) silently returns self instead of switching
                # user, so posting this as a company-restricted user would
                # crash with a bare AccessError and abort every move still
                # queued behind it in this loop. Skip only this move's
                # attachment copy instead.
                _logger.warning(
                    "Skipping the inter-company attachment copy for %s:"
                    " no inter-company user is configured on %s.",
                    ico_move.display_name,
                    ico_move.company_id.display_name,
                )
                continue

            ico_move.message_main_attachment_id = (
                self.env["ir.attachment"]
                .with_user(ico_move.company_id.intercompany_user_id.id)
                .with_company(ico_move.company_id.id)
                .create(
                    {
                        "name": attachment_name,
                        "type": "binary",
                        "mimetype": "application/pdf",
                        "raw": move_attachment.raw,
                        "res_model": "account.move",
                        "res_id": ico_move.id,
                    }
                )
            )

        return res
