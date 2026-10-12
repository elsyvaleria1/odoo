from __future__ import annotations

import logging
from functools import cache

from rapidocr import RapidOCR

from odoo.libs.documents import METERED, TEXT, BaseReader, register_reader

from odoo.addons.extract.tools import PAGE_BREAK, PAGED

_logger = logging.getLogger(__name__)


@cache
def _get_engine() -> RapidOCR:
    return RapidOCR()


def read_page(image: bytes) -> str:
    return "\n".join(_get_engine()(image).txts or ())


class OcrText(BaseReader):
    name = "rapidocr_text"
    mimetypes = PAGED
    yields = (TEXT,)
    cost = METERED
    module = "extract_ocr"

    def read(self, document):
        pages = document.images
        if not pages:
            return ""
        text = PAGE_BREAK.join(read_page(page) for page in pages).strip()
        if text:
            _logger.info(
                "%r had no text of its own; %d characters were read from its pages",
                document.name,
                len(text),
            )
        return text


register_reader(OcrText())
