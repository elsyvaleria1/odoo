import io
import zipfile

from werkzeug.utils import secure_filename

from odoo import http
from odoo.http import Stream, request


class WhatsappSign(http.Controller):
    def _split_filename(self, filename):
        dot_index = filename.rfind(".")

        if dot_index <= 0:
            return filename, ""

        base_name = filename[:dot_index]
        ext = filename[dot_index:]
        return base_name, ext

    def _generate_sign_request_zip_name(self, sign_request):
        subject = sign_request.subject
        if subject:
            name, _ = self._split_filename(subject)
        else:
            name = request.env._(
                "Attachments of Request %s", str(sign_request.reference)
            )

        return secure_filename(name)

    def _create_zip_response(self, sign_request):
        buffer = io.BytesIO()
        with zipfile.ZipFile(
            buffer, "w", compression=zipfile.ZIP_DEFLATED
        ) as zipfile_obj:
            existing_document_names = set()
            for attachment in sign_request.attachment_ids:
                download_name = self._format_attachments_name(
                    sign_request, attachment, existing_document_names
                )
                zipfile_obj.writestr(download_name, attachment.raw)

        content = buffer.getvalue()
        filename = f"{self._generate_sign_request_zip_name(sign_request)}.zip"

        return Stream(
            type="data",
            data=content,
            mimetype="application/zip",
            download_name=filename,
            as_attachment=True,
            size=len(content),
        ).prepare_response()

    def _format_attachments_name(
        self, sign_request, attachment, existing_document_names
    ):
        zip_name = self._generate_sign_request_zip_name(sign_request)
        base_name, ext = self._split_filename(attachment.name)
        download_name = attachment.name
        counter = 1

        while download_name in existing_document_names:
            download_name = f"{base_name} ({counter}){ext}"
            counter += 1
        existing_document_names.add(download_name)

        return f"{zip_name}/{download_name}" if zip_name else download_name

    @http.route(
        [
            "/sign/download/attachments/<int:request_id>/<token>",
            "/sign/download/attachments/<int:request_id>/<token>/<int:sign_attachment_id>",
        ],
        type="http",
        auth="public",
    )
    def download_attachment(self, request_id, token, sign_attachment_id=None, **post):
        sign_request = request.env["sign.request"]._from_request_token(
            token, request_id
        )
        if not sign_request:
            raise request.prepare_not_found_error()

        if sign_attachment_id:
            attachment = request.env["ir.attachment"].sudo().browse(sign_attachment_id)
            if attachment in sign_request.attachment_ids:
                return attachment._to_http_stream().prepare_response(as_attachment=True)
            else:
                raise request.prepare_not_found_error()

        attachment_ids = sign_request.attachment_ids
        if len(attachment_ids) == 1:
            return attachment_ids._to_http_stream().prepare_response(as_attachment=True)
        elif len(attachment_ids) > 1:
            return self._create_zip_response(sign_request)

        raise request.prepare_not_found_error()
