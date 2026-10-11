import base64
import io
import logging
import lzma
import uuid
from datetime import UTC, datetime
from functools import cache
from hashlib import sha256
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin as url_join

from cryptography import x509
from cryptography.x509.oid import NameOID

from odoo import http
from odoo.exceptions import ValidationError
from odoo.http import request
from odoo.libs.json import dumps_bytes as json_dumps_bytes
from odoo.tools import file_open
from odoo.tools.pdf import PdfReader, PdfReadError, PdfWriter
from odoo.tools.pdf.signature import PdfSignatureError, get_verified_pdf_signature

from odoo.addons.iap import jsonrpc
from odoo.addons.sign.controllers.main import Sign as SignController
from odoo.addons.sign_emsigner.const import IAP_DEFAULT_DOMAIN
from odoo.addons.sign_emsigner.utils import compress_pdf_base64

if TYPE_CHECKING:
    from odoo.addons.sign.models.sign_request_item import SignRequestItem

IAP_SERVICE_NAME = "emsigner_proxy"
TRUST_ROOTS = (
    "sign_emsigner/data/trust/cca_india_2022.pem",
    "sign_emsigner/data/trust/cca_india_2022_spl.pem",
)

_logger = logging.getLogger(__name__)


@cache
def _emsigner_trust_roots():
    roots = []
    for path in TRUST_ROOTS:
        with file_open(path, "rb") as pem:
            roots.append(x509.load_pem_x509_certificate(pem.read()))
    return tuple(roots)


def _common_name(certificate):
    names = certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    return names[0].value if names else certificate.subject.rfc4514_string()


class SignEmsigner(SignController):
    def _prepare_document_rendering_data(self, sign_request_id, token, **post):
        res = super()._prepare_document_rendering_data(sign_request_id, token, **post)
        if res.get("rendering_context"):
            res["rendering_context"]["show_emsigner_thank_you_dialog"] = post.get(
                "show_emsigner_thank_you_dialog"
            )
            res["rendering_context"]["error_message"] = post.get("error_message")
        return res

    def _get_signature_fields_position(self, document_id, request_item_sudo):
        try:
            pdf_file_data = io.BytesIO(document_id.attachment_id.raw)
            pdf_file_reader = PdfReader(pdf_file_data, strict=False)
            len(pdf_file_reader.pages)
        except (ValueError, PdfReadError) as e:
            raise ValidationError(
                self.env._("ERROR: Invalid PDF file! %s") % str(e)
            ) from e

        page_size = document_id._get_page_size(pdf_file_reader)
        pdf_width = float(page_size[0])
        pdf_height = float(page_size[1])

        signature_item_ids = request_item_sudo._get_current_signature_sign_items()

        return [
            {
                "page": item.page,
                "left": pdf_width * item.posX,
                "top": pdf_height * (1 - item.posY),
                "width": (pdf_width * item.posX) + (pdf_width * item.width),
                "height": pdf_height * (1 - item.posY - item.height),
            }
            for item in signature_item_ids
        ]

    def _is_file_large(self, file_size) -> bool:
        return file_size >= (1024 * 1024 * 9)

    def _bind_to_attempt(self, pdf, reference_number):
        writer = PdfWriter(io.BytesIO(pdf), incremental=True)
        writer.add_metadata({"/OdooSignAttempt": reference_number})
        bound = io.BytesIO()
        writer.write(bound)
        return bound.getvalue()

    def _generate_emsigner_request(
        self, request_item_sudo: SignRequestItem, **kwargs: Any
    ) -> dict[str, str | bool | int]:
        sign_request = request_item_sudo.sign_request_id
        document_id = sign_request.template_id.document_ids

        if len(document_id) != 1:
            raise ValidationError(
                self.env._(
                    "Emsigner only supports signing a single document at a time."
                )
            )

        signed_values = sign_request.sudo()._get_signed_values()

        signature_info = kwargs.get("signatureInfo", {})
        frame_info = kwargs.get("frame", {})

        for key_str, value in signature_info.items():
            key = int(key_str)
            frame_data = frame_info.get(key_str, {})
            signed_values[key] = {
                "value": value,
                "frame": frame_data.get("frameValue"),
                "frame_has_hash": bool(frame_data.get("frameHash")),
            }

        final_log_hash = sign_request._get_final_signature_log_hash()
        output = document_id.render_document_with_items(
            signed_values, final_log_hash=final_log_hash
        )
        reference_number = uuid.uuid4().hex
        to_sign_data = self._bind_to_attempt(output.getvalue(), reference_number)
        output.close()
        request_item_sudo.write(
            {
                "emsigner_document_sha256": sha256(to_sign_data).hexdigest(),
                "emsigner_document_size": len(to_sign_data),
            }
        )

        signature_position = self._get_signature_fields_position(
            document_id, request_item_sudo
        )
        page_numbers = ",".join(str(item["page"]) for item in signature_position)
        page_coordinates_with_page = ";".join(
            [
                f"{item['page']},{item['left'] + 8},{item['top'] - (item['top'] - item['height'])},{item['width']},{item['height'] - 20}"
                for item in signature_position
            ]
        )

        is_file_large = self._is_file_large(
            file_size=document_id.attachment_id.file_size
        )
        if is_file_large:
            to_sign_data = compress_pdf_base64(to_sign_data)

        dyamic_content = [
            {
                "Key": "eSigned using Aadhaar by",
                "Value": request_item_sudo.partner_id.email,
            },
            {"Key": "Date", "Value": "DateTime"},
        ]
        dyamic_content_bytes = json_dumps_bytes(dyamic_content)
        dyamic_content_data = base64.b64encode(dyamic_content_bytes)

        return {
            "Name": request_item_sudo.partner_id.name,
            "FileType": "PDF",
            "SignatureMode": "12",
            "SelectPage": "PAGE LEVEL",
            "File": base64.b64encode(to_sign_data).decode("utf-8"),
            "PageNumber": page_numbers,
            "PreviewRequired": False,
            "PagelevelCoordinates": page_coordinates_with_page,
            "ReferenceNumber": reference_number,
            "EnableUploadSignature": False,
            "EnableFontSignature": False,
            "EnableDrawSignature": False,
            "EnableESignaturePad": False,
            "IsCompressed": is_file_large,
            "IsCosign": False,
            "StoreToDB": True,
            "IsGSTN": False,
            "IsGSTN3B": False,
            "AuthenticationMode": 1,
            "Reason": f"Digitally Signed by {request_item_sudo.partner_id.email}",
            "DynamicContent": dyamic_content_data.decode("utf-8"),
        }

    def _acquire_auth_method_result(
        self, request_item_sudo: SignRequestItem, **kwargs
    ) -> dict[str, Any]:
        if request_item_sudo.role_id.auth_method == "emsigner":
            account = (
                request.env["iap.account"].sudo().acquire_account(IAP_SERVICE_NAME)
            )
            if not account.sudo().account_token:
                return {
                    "success": False,
                    "message": request.env._(
                        "emSigner IAP service could not be found."
                    ),
                }
            endpoint = request.env.registry.settings.get(
                request.env, "sign_emsigner.iap_endpoint", IAP_DEFAULT_DOMAIN
            )
            emsigner_credits = (
                request.env["iap.account"].sudo().get_credits(IAP_SERVICE_NAME)
            )
            if emsigner_credits < 1:
                request_item_sudo.signed_without_extra_auth = True
                return {"success": True}
            params = {
                "signature_data": self._generate_emsigner_request(
                    request_item_sudo, **kwargs
                ),
                "account_token": account.sudo().account_token,
                "emsigner_state": "%s.%s"
                % (
                    request_item_sudo.sign_request_id.id,
                    request_item_sudo.access_token,
                ),
                "db_uuid": self.env.registry.settings.get(
                    self.env, "database.uuid", False
                ),
                "url": account.get_base_url(),
            }
            return jsonrpc(
                url_join(endpoint, "/api/emsigner/1/sign_identity_request"),
                params=params,
            )
        return super()._acquire_auth_method_result(request_item_sudo, **kwargs)


    @http.route(
        "/emsigner_sign/emsigner_successful",
        type="jsonrpc",
        auth="public",
        csrf="false",
    )
    def sign_emsigner_complete(
        self,
        emsigner_state,
        reference_number,
        transaction_number,
        return_status,
        error_message,
        decrypted_data,
    ):
        if not emsigner_state or error_message or not decrypted_data:
            return {"success": False}
        sign_request_id, _dot, token = emsigner_state.partition(".")
        if not sign_request_id.isdigit():
            return {"success": False}
        request_item = request.env["sign.request.item"]._from_signer_token(
            token, request_id=sign_request_id
        )
        if not (
            request_item.state == "sent"
            and request_item.role_id.auth_method == "emsigner"
        ):
            return {"success": False}

        sign_request = request_item.sign_request_id
        document_id = sign_request.template_id.document_ids
        if len(document_id) != 1:
            raise ValidationError(
                self.env._(
                    "Emsigner only supports signing a single document at a time."
                )
            )

        try:
            signed_pdf = base64.b64decode(decrypted_data, validate=True)
            if self._is_file_large(file_size=document_id.attachment_id.file_size):
                signed_pdf = lzma.decompress(signed_pdf, format=lzma.FORMAT_ALONE)
            verified = get_verified_pdf_signature(
                signed_pdf, _emsigner_trust_roots(), datetime.now(UTC)
            )
        except (ValueError, lzma.LZMAError, PdfSignatureError) as e:
            _logger.warning(
                "emSigner result refused for sign request item %s: %s",
                request_item.id,
                e,
            )
            return {"success": False}
        if not request_item._emsigner_sent_document_matches(
            signed_pdf, verified.contents_offset
        ):
            _logger.warning(
                "emSigner result refused for sign request item %s: it does not "
                "sign the document sent for it",
                request_item.id,
            )
            return {"success": False}

        sign_user_sudo = (
            request.env["res.users"]
            .sudo()
            .search([("partner_id", "=", request_item.partner_id.id)], limit=1)
        )
        if sign_user_sudo:
            context = {}
            if request.env.user != sign_user_sudo and not request.env.user._is_public():
                context.update(logged_user_id=request.env.user.id)
            request_item = (
                request_item.with_context(context).with_user(sign_user_sudo).sudo()
            )

        sign_request.completed_document_ids = (
            request.env["sign.completed.document"]
            .sudo()
            .create(
                {
                    "sign_request_id": sign_request.id,
                    "file": base64.b64encode(signed_pdf),
                    "document_id": document_id.id,
                }
            )
        )

        request_item._write_emsigner_data(
            reference_number,
            transaction_number,
            return_status,
            _common_name(verified.signer),
        )
        request_item._post_fill_request_item()

        return {"success": True}


    @http.route(["/emsigner/has_emsigner_credits"], type="jsonrpc", auth="public")
    def has_emsigner_credits(self) -> bool:
        return request.env["iap.account"].sudo().get_credits(IAP_SERVICE_NAME) >= 1
