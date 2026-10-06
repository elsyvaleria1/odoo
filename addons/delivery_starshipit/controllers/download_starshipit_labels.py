from odoo import http
from odoo.http import prepare_content_disposition_header, request


class StarshipitDocumentDownloadController(http.Controller):
    @http.route(
        '/delivery_starshipit/download_starshipit_labels/<models("ir.attachment"):attachments>',
        type="http",
        auth="user",
    )
    def download_invoice_attachments(self, attachments):
        attachments.check_access("read")
        assert all(
            attachment.res_id and attachment.res_model == "stock.picking"
            for attachment in attachments
        )
        if len(attachments) == 1:
            return request.prepare_response(
                attachments.raw,
                [
                    ("Content-Type", attachments.mimetype),
                    ("Content-Length", len(attachments.raw)),
                    (
                        "Content-Disposition",
                        prepare_content_disposition_header(attachments.name),
                    ),
                    ("X-Content-Type-Options", "nosniff"),
                ],
            )
        else:
            filename = self.env._("starshipit_labels") + ".zip"
            content = attachments._prepare_zip_from_attachments()
            return request.prepare_response(
                content,
                [
                    ("Content-Type", "zip"),
                    ("Content-Length", len(content)),
                    (
                        "Content-Disposition",
                        prepare_content_disposition_header(filename),
                    ),
                    ("X-Content-Type-Options", "nosniff"),
                ],
            )
