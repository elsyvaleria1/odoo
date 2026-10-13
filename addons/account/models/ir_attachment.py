from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog
from odoo.libs.filesystem import guess_mimetype
from odoo.tools.misc import format_date

from odoo.addons.account.tools.zip_archive import prepare_zip_from_data

_debug = DebugLog(__name__)


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    @_debug.perf.timed
    def _prepare_zip_from_attachments(self):
        return prepare_zip_from_data(
            [
                {"filename": attachment.display_name, "content": attachment.raw}
                for attachment in self
            ]
        )

    def _filter_restricted_audit_trail(self):
        move_attachments = self.filtered(
            lambda attachment: (
                attachment.res_model == "account.move" and attachment.res_id
            )
        )
        if not move_attachments:
            return move_attachments
        restricted_move_ids = set(
            self.env["account.move"]
            .browse(set(move_attachments.mapped("res_id")))
            .exists()
            .filtered(
                lambda move: (
                    move.posted_before
                    and move.company_id.account_config_id.restrictive_audit_trail
                )
            )
            .ids
        )
        _debug.logic(
            "audit_trail_moves_restricted",
            attachments=move_attachments,
            restricted_moves=len(restricted_move_ids),
        )
        return move_attachments.filtered(
            lambda attachment: attachment.res_id in restricted_move_ids
        )

    @api.ondelete(at_uninstall=True)
    @_debug.perf.timed
    def _except_audit_trail(self) -> None:
        _debug.lifecycle("_except_audit_trail", records=self)
        restricted = self._filter_restricted_audit_trail()
        for attachment in restricted.with_prefetch(restricted._ids):
            if attachment.raw and guess_mimetype(attachment.raw) in (
                "application/pdf",
                "application/xml",
            ):
                ue = UserError(
                    self.env._("You cannot remove parts of a restricted audit trail.")
                )
                ue._audit_trail = True
                raise ue

    @_debug.perf.timed
    def write(self, vals):
        _debug.lifecycle("write", records=self, fields=sorted(vals))
        if vals.keys() & {
            "res_id",
            "res_model",
            "raw",
            "datas",
            "store_fname",
            "db_datas",
            "company_id",
        }:
            try:
                self._except_audit_trail()
            except UserError as e:
                if (
                    not hasattr(e, "_audit_trail")
                    or vals.get("res_model") != "document.document"
                    or vals.keys() & {"raw", "datas", "store_fname", "db_datas"}
                ):
                    raise
                _debug.logic(
                    "audit_trail_relinked_document", records=self, fields=sorted(vals)
                )
                vals.pop("res_model", None)
                vals.pop("res_id", None)
        return super().write(vals)

    @_debug.perf.timed
    def unlink(self):
        _debug.lifecycle("unlink", unlink=self)
        invoice_pdf_attachments = self.filtered(
            lambda attachment: (
                attachment.res_field in ("invoice_pdf_report_file", "ubl_cii_xml_file")
            )
        )._filter_restricted_audit_trail()
        _debug.logic(
            "audit_pdfs_detached",
            detached=invoice_pdf_attachments,
            unlinked=len(self) - len(invoice_pdf_attachments),
        )
        if invoice_pdf_attachments:
            invoice_pdf_attachments.res_field = False
            today = format_date(self.env, fields.Date.context_today(self))
            for attachment in invoice_pdf_attachments:
                attachment_name = attachment.name
                attachment_extension = ""
                dot_index = attachment_name.rfind(".")
                if dot_index > 0:
                    attachment_name = attachment.name[:dot_index]
                    attachment_extension = attachment.name[dot_index:]
                attachment.name = self.env._(
                    "%(attachment_name)s (detached by %(user)s on %(date)s)%(attachment_extension)s",
                    attachment_name=attachment_name,
                    attachment_extension=attachment_extension,
                    user=self.env.user.name,
                    date=today,
                )
        return super(IrAttachment, self - invoice_pdf_attachments).unlink()

    @_debug.perf.timed
    def _post_add_create(self, **kwargs):
        _debug.lifecycle("_post_add_create", records=self)
        for move_id, attachments in (
            self.filtered(lambda attachment: attachment.res_model == "account.move")
            .grouped("res_id")
            .items()
        ):
            move = self.env["account.move"].browse(move_id)
            files_data = move._to_files_data(attachments)
            files_data.extend(move._unwrap_attachments(files_data))
            move._extend_with_attachments(files_data)
        super()._post_add_create(**kwargs)
