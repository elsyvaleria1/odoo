import base64

from odoo import api, fields, models


class WizardSignTemplatePreview(models.TransientModel):
    _name = "wizard.sign.template.preview"
    _description = "Sign Tempate Preview"

    template_id = fields.Many2one(
        comodel_name="sign.template",
        ondelete="cascade",
    )
    document_id = fields.Many2one(
        comodel_name="sign.document",
        ondelete="cascade",
    )
    pdf_data = fields.Binary(compute="_compute_pdf")

    @api.depends("template_id")
    def _compute_pdf(self) -> None:
        for wiz in self:
            if not wiz.template_id:
                continue
            wiz.template_id.check_access("read")
            wiz.document_id.check_access("read")
            document = wiz.document_id.with_context(bin_size=False)
            output = document.render_document_with_items(
                document._prepare_preview_vals()
            )
            pdf_data = base64.b64encode(output.getvalue())
            output.close()
            wiz.pdf_data = pdf_data
