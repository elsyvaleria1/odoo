from werkzeug.exceptions import BadRequest

from odoo.http import Stream, request, route
from odoo.libs.debug_log import DebugLog
from odoo.tools import replace_exceptions, str2bool

from odoo.addons.document.controllers.document import ShareRoute

_debug = DebugLog(__name__)


class AccountShareRoute(ShareRoute):
    @route()
    def documents_content(self, access_token, download=True):
        with replace_exceptions(ValueError, by=BadRequest):
            download = str2bool(download)
        if download:
            return super().documents_content(access_token, download)
        document_sudo = self._from_access_token(access_token, skip_log=True)
        if document_sudo.type != "binary" or not document_sudo.has_embedded_pdf:
            return super().documents_content(access_token, download)
        embedded_pdf = document_sudo._extract_pdf_from_xml()
        _debug.pipeline("content_served", by="embedded_pdf", document=document_sudo)
        self._log_view(document_sudo)
        return Stream(
            type="data",
            data=embedded_pdf,
            mimetype="application/pdf",
            download_name=f"{document_sudo.name}.pdf",
            size=len(embedded_pdf),
            public=request.env.user._is_public(),
        ).prepare_response(as_attachment=False)
