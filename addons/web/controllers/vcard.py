import functools
import importlib.util
import io
import zipfile

from odoo import http
from odoo.exceptions import UserError
from odoo.http import Response, prepare_content_disposition_header, request
from odoo.libs.debug_log import DebugLog
from odoo.libs.filesystem import osutil

from .utils import parse_id_list

_debug = DebugLog(__name__)


@functools.cache
def _has_vobject() -> bool:
    return importlib.util.find_spec("vobject") is not None


def _get_vcard_label(partner) -> str:
    return partner.name or partner.email or f"contact_{partner.id}"


def _prepare_download(content: bytes, content_type: str, filename: str) -> Response:
    return request.prepare_response(
        content,
        [
            ("Content-Type", content_type),
            ("Content-Disposition", prepare_content_disposition_header(filename)),
        ],
    )


class Partner(http.Controller):
    @http.route(
        [
            '/web_enterprise/partner/<model("res.partner"):partner>/vcard',
            "/web/partner/vcard",
        ],
        type="http",
        auth="user",
        readonly=True,
    )
    def download_vcard(self, partner_ids=None, partner=None, **kwargs):
        _debug.lifecycle(
            "vcard_download",
            partner=partner.id if partner else None,
            partner_ids=partner_ids,
        )
        if not _has_vobject():
            _debug.logic("vcard_vobject_missing")
            raise UserError(request.env._("vobject library is not installed"))

        partners = partner or request.env["res.partner"].browse(
            list(dict.fromkeys(parse_id_list(partner_ids)))
        )
        _debug.logic(
            "vcard_mode",
            mode="zip" if len(partners) > 1 else "single",
            partners=partners,
        )
        if not partners:
            _debug.logic("vcard_no_partner_not_found")
            raise request.prepare_not_found_error()

        if len(partners) == 1:
            with _debug.perf("vcard_render", cr=request.env.cr, partners=partners):
                content = partners._get_vcard_file()
            _debug.pipeline("vcard_single_ready", partners=partners, size=len(content))
            return _prepare_download(
                content,
                "text/vcard",
                osutil.clean_filename(f"{_get_vcard_label(partners)}.vcf"),
            )

        buffer = io.BytesIO()
        with (
            _debug.perf("vcard_zip", cr=request.env.cr, partners=len(partners)),
            zipfile.ZipFile(buffer, "w") as zipf,
        ):
            used_names = set()
            for p in partners:
                label = _get_vcard_label(p)
                name = osutil.clean_filename(f"{label}.vcf")
                candidate, i = name, 1
                while candidate in used_names:
                    candidate = osutil.clean_filename(f"{label} ({i}).vcf")
                    i += 1
                used_names.add(candidate)
                zipf.writestr(candidate, p._get_vcard_file())
        zip_data = buffer.getvalue()
        _debug.pipeline("vcard_zip_ready", entries=len(used_names), size=len(zip_data))
        return _prepare_download(zip_data, "application/zip", "Contacts.zip")
