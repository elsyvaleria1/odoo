from __future__ import annotations

import io
import logging

import zxingcpp
from PIL import Image

from odoo.libs.documents import BARCODES, CHEAP, BaseReader, register_reader

from odoo.addons.extract.tools import PAGED

_logger = logging.getLogger(__name__)


def read_page(image: bytes) -> list[str]:
    return [
        symbol.text for symbol in zxingcpp.read_barcodes(Image.open(io.BytesIO(image)))
    ]


class Barcodes(BaseReader):

    name = "zxing_barcodes"
    mimetypes = PAGED
    yields = (BARCODES,)
    cost = CHEAP
    module = "extract_barcode"

    def read(self, document):
        pages = document.images
        if not pages:
            return []
        found: list[str] = []
        for page in pages:
            try:
                found.extend(read_page(page))
            except Exception as e:
                _logger.warning(
                    "Barcode reader failed on a page of %r: %s",
                    document.name,
                    e,
                    exc_info=True,
                )
        return list(dict.fromkeys(found))


register_reader(Barcodes())
