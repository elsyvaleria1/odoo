import io

from odoo import models
from odoo.tools.pdf import OdooPdfFileReader, OdooPdfFileWriter


class IrActionsReport(models.Model):
    _inherit = "ir.actions.report"

    def _render_qweb_pdf_prepare_streams(self, report_ref, data, res_ids=None):
        collected_streams = super()._render_qweb_pdf_prepare_streams(
            report_ref, data, res_ids=res_ids
        )

        if (
            collected_streams
            and res_ids
            and len(res_ids) == 1
            and self._is_invoice_report(report_ref)
        ):
            invoice = self.env["account.move"].browse(res_ids)
            if invoice.is_sale_document() and invoice.state != "draft":
                to_embed = invoice.edi_document_ids
                if to_embed:
                    pdf_stream = collected_streams[invoice.id]["stream"]

                    pdf_content = pdf_stream.getvalue()
                    reader_buffer = io.BytesIO(pdf_content)
                    reader = OdooPdfFileReader(reader_buffer, strict=False)

                    writer = OdooPdfFileWriter()
                    writer.clone_reader_document_root(reader)
                    for edi_document in to_embed:
                        edi_document.edi_format_id._prepare_invoice_report(
                            writer, edi_document
                        )

                    pdf_stream.close()
                    new_pdf_stream = io.BytesIO()
                    writer.write(new_pdf_stream)
                    collected_streams[invoice.id]["stream"] = new_pdf_stream

        return collected_streams
