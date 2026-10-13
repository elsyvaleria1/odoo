from collections.abc import Iterable, Mapping
from typing import Any, override

import zeep
from zeep.exceptions import ExternalReferenceForbidden

from odoo.tools.files import file_open


def _location(url: str) -> str:
    return url.partition("://")[2]


def shipped_documents(
    base_url: str, directory: str, names: Iterable[str]
) -> dict[str, str]:
    return {f"{base_url}/{name}": f"{directory}/{name}" for name in names}


class ShippedDocumentsTransport(zeep.Transport):  # noqa: E8518 - loads every WSDL and XSD from disk; sends through the ir.egress session it is given
    def __init__(self, documents: Mapping[str, str], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._documents = {_location(url): path for url, path in documents.items()}

    @override
    def load(self, url: str) -> bytes:
        path = self._documents.get(_location(url))
        if path is None:
            raise ExternalReferenceForbidden(url)
        with file_open(path, "rb") as document:
            content: bytes = document.read()
        return content
