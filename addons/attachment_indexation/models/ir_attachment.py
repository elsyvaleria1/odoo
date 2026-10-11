import importlib.util
import io
import logging

from odoo import api, models
from odoo.libs.documents import Document, canonical_mimetypes

from ..tools.readers import (
    clean_text_content,
    read_docx,
    read_opendoc,
    read_pptx,
    read_xlsx,
)

_logger = logging.getLogger(__name__)

if not (
    importlib.util.find_spec("pdfminer")
    and importlib.util.find_spec("pdfminer.high_level")
):
    _logger.warning(
        "Attachment indexation of PDF documents is unavailable because the 'pdfminer.six' Python library cannot be found on the system. "
        "You may install it from https://pypi.org/project/pdfminer.six/ (e.g. `pip3 install pdfminer.six`)"
    )


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    def _index_docx(self, bin_data):
        return read_docx(bin_data, self._INDEX_MAX_BYTES)

    def _index_pptx(self, bin_data):
        return read_pptx(bin_data, self._INDEX_MAX_BYTES)

    def _index_xlsx(self, bin_data):
        return read_xlsx(bin_data, self._INDEX_MAX_BYTES)

    def _index_opendoc(self, bin_data):
        return read_opendoc(bin_data, self._INDEX_MAX_BYTES)

    def _index_pdf(self, bin_data):
        if not bin_data.startswith(b"%PDF-"):
            return ""
        try:
            if not importlib.util.find_spec("pdfminer.high_level"):
                return ""
            from pdfminer.converter import TextConverter
            from pdfminer.layout import LAParams
            from pdfminer.pdfinterp import (
                PDFPageInterpreter,
                PDFResourceManager,
            )
            from pdfminer.pdfpage import PDFPage

            logging.getLogger("pdfminer").setLevel(logging.CRITICAL)
        except ImportError:
            return ""
        f = io.BytesIO(bin_data)
        try:
            resource_manager = PDFResourceManager()
            laparams = LAParams(detect_vertical=True, boxes_flow=None)

            with (
                io.StringIO() as content,
                TextConverter(resource_manager, content, laparams=laparams) as device,
            ):
                interpreter = PDFPageInterpreter(resource_manager, device)
                for page in PDFPage.get_pages(f):
                    interpreter.process_page(page)

                buf = content.getvalue()
            return clean_text_content(buf)
        except Exception:
            _logger.debug(
                "attachment_indexation: failed to index pdf content", exc_info=True
            )
            return ""

    @api.model
    def _get_index_content(self, bin_data, mimetype):
        if not bin_data or (mimetype or "").startswith("text/"):
            return super()._get_index_content(bin_data, mimetype)

        document = Document(
            bin_data,
            mimetype,
            text_max_chars=self._get_index_max_chars(),
            max_zip_entry_bytes=self._INDEX_MAX_BYTES,
        )
        if document.mimetype == "application/pdf":
            res = self._index_pdf(bin_data)
        else:
            res = document.text
        res = res.replace("\x00", "") if res else False

        return res or super()._get_index_content(bin_data, mimetype)

    _INDEXED_DOC_MIMETYPES = canonical_mimetypes(
        "pdf", "docx", "xlsx", "pptx", "odt", "ods", "odp", "odg"
    )

    @api.model
    def _get_index_read_size(self, mimetype):
        if (
            not mimetype
            or mimetype == "application/octet-stream"
            or mimetype in self._INDEXED_DOC_MIMETYPES
        ):
            return None
        return super()._get_index_read_size(mimetype)
