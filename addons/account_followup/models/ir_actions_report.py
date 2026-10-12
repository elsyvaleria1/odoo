import io

from odoo import models
from odoo.tools.pdf import OdooPdfFileReader, OdooPdfFileWriter, to_pdf_stream

from .followup_request import FollowupRequest


class IrActionsReport(models.Model):
    _inherit = "ir.actions.report"

    def _prepare_rendering_context(self, report, docids, data):
        if report.report_name == "account_followup.report_followup_print_all":
            data = dict(data or {})
            data.setdefault("followup_request", None)
        return super()._prepare_rendering_context(report, docids, data)

    def _render_qweb_pdf_prepare_streams(self, report_ref, data, res_ids=None):
        res = super()._render_qweb_pdf_prepare_streams(report_ref, data, res_ids)
        report = self._get_report(report_ref)
        if (
            not res_ids
            or report.report_name != "account_followup.report_followup_print_all"
        ):
            return res

        request = data.get("followup_request")
        for partner_id in res_ids:
            partner = self.env["res.partner"].browse(partner_id)
            partner_request = (request or FollowupRequest.prepare(partner)).replace(
                partner=partner
            )
            if not partner_request.join_invoices and not (
                partner_request.report_attachment_id
            ):
                continue

            if partner_request.attachment_ids:
                attachments = self.env["ir.attachment"].browse(
                    list(partner_request.attachment_ids)
                )
            else:
                invoices = partner._get_invoices_to_print(partner_request)
                attachments = invoices.message_main_attachment_id

            writer = OdooPdfFileWriter()

            followup_stream = res[partner_id]["stream"]
            input_streams = [followup_stream] + [
                to_pdf_stream(attachment)
                for attachment in self._migrate_attachments_to_local(attachments)
                if attachment.mimetype == "application/pdf"
            ]
            for stream in input_streams:
                reader = OdooPdfFileReader(stream, strict=False)
                writer.append_pages_from_reader(reader)

            output_stream = io.BytesIO()
            writer.write(output_stream)
            res[partner_id]["stream"] = output_stream
            for stream in input_streams:
                stream.close()

        return res
