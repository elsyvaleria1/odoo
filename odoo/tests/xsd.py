import base64
import contextlib
import logging
import typing
import zipfile
from io import BytesIO
from typing import Any, Literal

import requests
from lxml import etree

from odoo.libs.debug_log import DebugLog
from odoo.tools.files import file_open
from odoo.tools.xml_utils import XmlSource, check_with_xsd

if typing.TYPE_CHECKING:
    from odoo.api import Environment
    from odoo.orm.runtime._model_types import IrAttachmentModel

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)


def _find_xsd_attachment(env: Environment, name: str) -> IrAttachmentModel:
    return env["ir.attachment"].search(
        [("name", "=", name), ("res_model", "=", False)], limit=1
    )


class odoo_resolver(etree.Resolver):
    def __init__(self, env: Environment, prefix: str | None) -> None:
        super().__init__()
        self.env = env
        self.prefix = prefix

    def resolve(self, url: str, id: object, context: object) -> object:
        for name in dict.fromkeys((url, url.rsplit("/", 1)[-1])):
            attachment_name = f"{self.prefix}.{name}" if self.prefix else name
            attachment = _find_xsd_attachment(self.env, attachment_name)
            if attachment:
                break
        _debug.logic(
            "xsd.import_resolved",
            url=url,
            attachment=attachment_name,
            found=bool(attachment),
        )
        if attachment:
            return self.resolve_string(attachment.raw, context)
        return None


def _pick_xsd(xsd_attachments: Any, xsd_name: str | None, source: str) -> str:
    if xsd_name:
        picked = xsd_attachments.filtered(lambda a: a.name.endswith(xsd_name))
        if not picked:
            available = ", ".join(sorted(xsd_attachments.mapped("name")))
            raise FileNotFoundError(
                f"{source} provided no XSD named {xsd_name!r}; it has: {available}"
            )
        picked_name: str = picked[0].name
        return picked_name
    if len(xsd_attachments) > 1:
        available = ", ".join(sorted(xsd_attachments.mapped("name")))
        raise ValueError(
            f"{source} provided {len(xsd_attachments)} schemas and none was "
            f"named: pass xsd_name= to say which one is the root. "
            f"Available: {available}"
        )
    only_name: str = xsd_attachments.name
    return only_name


def check_with_attachment_xsd(
    xml_content: XmlSource, xsd_name: str, env: Environment, prefix: str | None = None
) -> None:
    attachment = _find_xsd_attachment(env, xsd_name)
    if not attachment:
        raise FileNotFoundError
    check_with_xsd(
        xml_content,
        BytesIO(attachment.raw or b""),
        resolvers=(odoo_resolver(env, prefix),),
    )


def check_xml(
    env: Environment,
    url: str | None,
    path: str | None,
    xmls: XmlSource | list[XmlSource],
    xsd_name: str | None = None,
) -> None:
    xsd_attachment: Any = env["ir.attachment"]
    owned: Any = env["ir.attachment"]
    if path:
        with file_open(path, filter_ext=(".xsd",)) as file:
            content = file.read()
        attachment_vals = {
            "name": path.split("/")[-1],
            "datas": base64.b64encode(content.encode()),
        }
        xsd_attachment = owned = env["ir.attachment"].create(attachment_vals)
    elif url:
        xsd_attachment = load_xsd_files_from_url(env, url) or env["ir.attachment"]

    try:
        if not xsd_attachment:
            raise FileNotFoundError(
                f"No XSD could be loaded from {url or path!r}; refusing to report "
                f"the document as validated."
            )

        name = _pick_xsd(xsd_attachment, xsd_name, repr(url or path))

        if not isinstance(xmls, list):
            xmls = [xmls]

        for xml in xmls:
            check_xml_from_attachment(env, xml, name)
    finally:
        owned.unlink()


def _upsert_xsd_attachment(
    env: Environment, name: str, content: bytes
) -> IrAttachmentModel:
    fetched_attachment = _find_xsd_attachment(env, name)
    _debug.lifecycle(
        "xsd.attachment_upserted",
        name=name,
        updated=bool(fetched_attachment),
        size=len(content),
    )
    if fetched_attachment:
        _logger.info("Updating the content of ir.attachment with name: %s", name)
        fetched_attachment.raw = content
        return fetched_attachment

    _logger.info("Saving XSD file as ir.attachment, with name: %s", name)
    return env["ir.attachment"].create({"name": name, "raw": content, "public": True})


_XSD_REQUEST_TIMEOUT = 10


def _get_xsd_content(url: str) -> bytes | None:
    try:
        _logger.info("Fetching file/archive from given URL: %s", url)
        with _debug.perf("xsd.fetched", url=url, timeout=_XSD_REQUEST_TIMEOUT) as span:
            response = requests.get(url, timeout=_XSD_REQUEST_TIMEOUT)
            span.set(
                status=getattr(response, "status_code", None),
                size=len(response.content),
            )
        response.raise_for_status()
    except requests.exceptions.RequestException as error:
        _logger.warning("Request error: %s with the given URL: %s", error, url)
        _debug.logic("xsd.fetch_failed", url=url, error=type(error).__name__)
        return None

    if not response.content:
        _logger.warning("The HTTP response from %s is empty (no content)", url)
        _debug.logic("xsd.fetch_failed", url=url, error="empty")
        return None
    content: bytes = response.content
    return content


def _load_xsd_archive(env: Environment, archive: zipfile.ZipFile) -> IrAttachmentModel:
    saved_attachments = env["ir.attachment"]
    for file_path in archive.namelist():
        if not file_path.endswith(".xsd"):
            continue
        file_name = file_path.rsplit("/", 1)[-1]
        try:
            content = archive.read(file_path)
        except KeyError:
            _logger.warning(
                "Failed to retrieve XSD file with name %s from ZIP archive", file_name
            )
            continue
        saved_attachments |= _upsert_xsd_attachment(env, file_name, content)

    _debug.pipeline(
        "xsd.archive_loaded",
        members=len(archive.namelist()),
        saved=len(saved_attachments),
    )
    return saved_attachments


def load_xsd_files_from_url(
    env: Environment, url: str
) -> IrAttachmentModel | Literal[False]:
    content = _get_xsd_content(url)
    if content is None:
        return False

    archive = None
    with contextlib.suppress(zipfile.BadZipFile):
        archive = zipfile.ZipFile(BytesIO(content))

    _debug.logic("xsd.source", url=url, archive=archive is not None, size=len(content))
    if archive is not None:
        return _load_xsd_archive(env, archive)
    return _upsert_xsd_attachment(env, url.rsplit("/", maxsplit=1)[-1], content)


def check_xml_from_attachment(
    env: Environment,
    xml_content: etree._Element | str | bytes,
    xsd_name: str,
    prefix: str | None = None,
    *,
    required: bool = True,
) -> None:
    prefixed_xsd_name = f"{prefix}.{xsd_name}" if prefix else xsd_name
    try:
        _logger.info("Validating with XSD...")
        check_with_attachment_xsd(xml_content, prefixed_xsd_name, env, prefix)
        _logger.info("XSD validation successful!")
    except FileNotFoundError:
        _debug.logic(
            "xsd.unavailable",
            schema=prefixed_xsd_name,
            reason="missing",
            required=required,
        )
        if required:
            raise FileNotFoundError(
                f"XSD {prefixed_xsd_name!r} is not available, so the document "
                f"could not be validated. Load the schema, or pass "
                f"required=False to accept an unvalidated document."
            ) from None
        _logger.warning(
            "XSD %r not found; the document was NOT validated", prefixed_xsd_name
        )
    except etree.XMLSchemaParseError as e:
        _debug.logic(
            "xsd.unavailable",
            schema=prefixed_xsd_name,
            reason="unparsable",
            required=required,
        )
        if required:
            raise FileNotFoundError(
                f"XSD {prefixed_xsd_name!r} could not be parsed, so the "
                f"document was not validated: {e}"
            ) from e
        _logger.warning(
            "XSD %r is not valid; the document was NOT validated: %s",
            prefixed_xsd_name,
            e,
        )
