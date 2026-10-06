from odoo import api, models
from odoo.libs.debug_log import DebugLog
from odoo.libs.documents import mimetypes_for

_debug = DebugLog(__name__)

# every spelling an XML file arrives under: a mail client sends text/xml
XML_MIMETYPES = mimetypes_for("xml")


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    @api.model_create_multi
    def create(self, vals_list):
        attachments = super().create(vals_list)
        for attachment in attachments:
            # Read the link from the created record, not from vals: res_model and
            # res_id may have been supplied through the default_res_model /
            # default_res_id context keys instead of the values dict.
            if attachment.res_model != "account.move":
                continue
            move = self.env["account.move"].browse(attachment.res_id)
            if _debug.logic.enabled:
                _debug.logic(
                    "move_document_gate",
                    by="create",
                    move=move,
                    move_type=move.move_type,
                    mimetype=attachment.mimetype,
                    no_document=bool(self.env.context.get("no_document")),
                )
            # To avoid creating extra documents, restrict document creation to:
            # - attachments of a misc operation
            # - an xml file once it has been successfully registered as a move attachment
            # and only when the 'no_document' flag is set to False
            if not self.env.context.get("no_document") and (
                move.move_type == "entry" or attachment.mimetype in XML_MIMETYPES
            ):
                _debug.pipeline(
                    "move_document_from_create",
                    move=move,
                    move_type=move.move_type,
                    mimetype=attachment.mimetype,
                )
                move._update_or_create_document(attachment.id)
        return attachments

    def write(self, vals):
        res = super().write(vals)

        if vals.get("res_model") == "account.move" and not self.env.context.get(
            "no_document"
        ):
            # Same restriction as create(): a misc operation, or an xml file once
            # it has been successfully registered as a move attachment. Moves the
            # user cannot read are left out by the search rather than raising.
            moves = self.env["account.move"].search(
                [("id", "in", self.mapped("res_id"))]
            )
            readable_ids = set(moves.ids)
            entry_ids = set(moves.filtered(lambda m: m.move_type == "entry").ids)
            for attachment in self:
                if _debug.logic.enabled:
                    _debug.logic(
                        "move_document_gate",
                        by="write",
                        move=attachment.res_id,
                        mimetype=attachment.mimetype,
                        readable=attachment.res_id in readable_ids,
                        is_entry=attachment.res_id in entry_ids,
                    )
                if attachment.res_id not in readable_ids:
                    continue
                if (
                    attachment.res_id in entry_ids
                    or attachment.mimetype in XML_MIMETYPES
                ):
                    move = self.env["account.move"].browse(attachment.res_id)
                    _debug.pipeline(
                        "move_document_from_write",
                        move=move,
                        mimetype=attachment.mimetype,
                    )
                    move._update_or_create_document(attachment.id)

        return res
