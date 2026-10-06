import base64

from odoo import fields, models
from odoo.exceptions import UserError
from odoo.tools.pdf.signature import PdfSigner


class SignCompletedDocument(models.Model):
    _name = "sign.completed.document"
    _description = "Completed Document"

    sign_request_id = fields.Many2one(
        comodel_name="sign.request",
        index=True,
        required=True,
        ondelete="restrict",
    )
    file = fields.Binary(
        string="Completed Document",
        attachment=True,
        copy=False,
        readonly=True,
    )
    document_id = fields.Many2one(
        comodel_name="sign.document",
        index=True,
        required=True,
        ondelete="restrict",
    )

    def _update_completed_document(self) -> None:
        signed_values_by_request = {
            sign_request.id: sign_request._get_signed_values()
            for sign_request in self.sign_request_id
        }
        for record in self:
            signed_values = signed_values_by_request[record.sign_request_id.id]
            final_log_hash = record.sign_request_id._get_final_signature_log_hash()
            output = record.document_id.render_document_with_items(
                signed_values, final_log_hash=final_log_hash
            )
            if output is None:
                raise UserError(
                    self.env._(
                        "The document cannot be completed because its PDF is encrypted."
                    )
                )
            signer = PdfSigner(output, record.sign_request_id.communication_company_id)
            signed_output = signer.sign_pdf(
                True,
                record.sign_request_id._get_signing_field_name(),
                record.sign_request_id.create_uid.partner_id,
            )
            if signed_output:
                output = signed_output
            record.file = base64.b64encode(output.getvalue())
            output.close()
