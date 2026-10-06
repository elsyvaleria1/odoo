from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import io
import logging
import re

from asn1crypto import algos, cms, core, x509

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec, ed25519, padding, rsa
    from cryptography.hazmat.primitives.asymmetric.types import PrivateKeyTypes
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        load_pem_private_key,
    )
    from cryptography.x509 import (
        BasicConstraints,
        Certificate,
        ExtensionNotFound,
        KeyUsage,
        SubjectKeyIdentifier,
        load_der_x509_certificate,
        load_pem_x509_certificate,
    )

    HAS_CRYPTOGRAPHY = True
except ImportError:  # pragma: no cover  exercised only where the wheel is absent
    HAS_CRYPTOGRAPHY = False

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any, NamedTuple

from odoo.libs.debug_log import DebugLog
from odoo.tools.pdf import (
    ArrayObject,
    ByteStringObject,
    DictionaryObject,
    NameObject,
    NumberObject,
    PdfReader,
    PdfWriter,
    create_string_object,
)
from odoo.tools.pdf import (
    DecodedStreamObject as StreamObject,
)

if TYPE_CHECKING:
    from pypdf import PageObject
    from pypdf.generic import IndirectObject

    from odoo.addons.base.models.res_company import ResCompany
    from odoo.addons.base.models.res_users import ResUsers

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)

_PDF_LITERAL_ESCAPES = str.maketrans({"\\": r"\\", "(": r"\(", ")": r"\)"})


def _escape_pdf_literal(text: str) -> str:
    return text.translate(_PDF_LITERAL_ESCAPES)


class PdfSignatureError(Exception):
    pass


class _SignatureAlgorithm(NamedTuple):
    digest: str
    signature: str
    sign: Callable[[bytes], bytes]


class PdfSigner:
    _CONTENTS_PLACEHOLDER_BYTES = 8192

    def __init__(
        self,
        stream: io.BytesIO,
        company: ResCompany | None = None,
        signing_time: datetime.datetime | None = None,
    ) -> None:
        moment = signing_time or datetime.datetime.now(datetime.UTC)
        self.signing_time = (
            moment.astimezone(datetime.UTC)
            if moment.tzinfo
            else moment.replace(tzinfo=datetime.UTC)
        )
        self.company = company
        self.writer = PdfWriter()
        self.writer.clone_document_from_reader(PdfReader(stream))

    def sign_pdf(
        self,
        visible_signature: bool = False,
        field_name: str = "Odoo Signature",
        signer: ResUsers | None = None,
    ) -> io.BytesIO | None:
        if not self.company or not HAS_CRYPTOGRAPHY:
            _debug.logic(
                "pdf.signature_skipped",
                company=getattr(self.company, "id", None),
                cryptography=HAS_CRYPTOGRAPHY,
            )
            return None

        with _debug.perf(
            "pdf.signed",
            company=getattr(self.company, "id", None),
            visible=visible_signature,
            field=field_name,
            signer=getattr(signer, "id", None),
        ) as span:
            _dummy, sig_field_value = self._setup_form(
                visible_signature, field_name, signer
            )

            signed = self._sign_field(sig_field_value)
            span.set(signed=signed)
            if not signed:
                return None

            out_stream = io.BytesIO()
            self.writer.write_stream(out_stream)
            span.set(output_bytes=out_stream.getbuffer().nbytes)
        return out_stream

    def _load_key_and_certificate(
        self,
    ) -> tuple[PrivateKeyTypes | None, Certificate | None]:
        company: Any = self.company
        if (
            company is None
            or "signing_certificate_id" not in company._fields
            or not company.signing_certificate_id.pem_certificate
        ):
            return None, None

        certificate = company.signing_certificate_id
        cert_bytes = base64.decodebytes(certificate.pem_certificate)
        private_key_bytes = base64.decodebytes(certificate.private_key_id.content)
        return load_pem_private_key(private_key_bytes, None), load_pem_x509_certificate(
            cert_bytes
        )

    def _acro_form(self) -> DictionaryObject:
        if "/AcroForm" not in self.writer._root_object:
            form = DictionaryObject()
            form.update({NameObject("/SigFlags"): NumberObject(3)})
            self.writer._root_object.update(
                {NameObject("/AcroForm"): self.writer._add_object(form)}
            )
        else:
            form = self.writer._root_object["/AcroForm"].get_object()
            form.update({NameObject("/SigFlags"): NumberObject(3)})
        return form

    @staticmethod
    def _appearance_resources() -> DictionaryObject:
        return DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject(
                    {
                        NameObject("/F1"): DictionaryObject(
                            {
                                NameObject("/Type"): NameObject("/Font"),
                                NameObject("/Subtype"): NameObject("/Type1"),
                                NameObject("/BaseFont"): NameObject("/Helvetica"),
                                NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
                            }
                        )
                    }
                )
            }
        )

    def _visible_appearance(
        self, page: PageObject, signer: ResUsers | None
    ) -> tuple[list[float], DictionaryObject]:
        origin = page.mediabox.upper_right
        rect_size = (200, 20)
        padding = 5
        rect = [
            origin[0] - rect_size[0] - padding,
            origin[1] - rect_size[1] - padding,
            origin[0] - padding,
            origin[1] - padding,
        ]

        stream = StreamObject()
        stream.update(
            {
                NameObject("/BBox"): self._create_number_array_object(
                    [0, 0, rect_size[0], rect_size[1]]
                ),
                NameObject("/Resources"): self._appearance_resources(),
                NameObject("/Type"): NameObject("/XObject"),
                NameObject("/Subtype"): NameObject("/Form"),
            }
        )

        content = "Digitally signed"
        if signer is not None:
            content = f"{content} by {signer.name} <{signer.email}>"

        stream._data = (
            f"q 0.5 0 0 0.5 0 0 cm BT /F1 12 Tf 0 TL 0 10 Td "
            f"({_escape_pdf_literal(content)}) Tj ET Q"
        ).encode("cp1252", errors="replace")
        signature_appearence = DictionaryObject()
        signature_appearence.update({NameObject("/N"): stream})
        return rect, signature_appearence

    def _signature_field_value(self) -> DictionaryObject:
        signature_field_value = DictionaryObject()
        signature_field_value.update(
            {
                NameObject("/Contents"): ByteStringObject(
                    b"\0" * self._CONTENTS_PLACEHOLDER_BYTES
                ),
                NameObject("/ByteRange"): self._create_number_array_object(
                    [0, 0, 0, 0]
                ),
                NameObject("/Type"): NameObject("/Sig"),
                NameObject("/Filter"): NameObject("/Adobe.PPKLite"),
                NameObject("/SubFilter"): NameObject("/adbe.pkcs7.detached"),
                NameObject("/M"): create_string_object(
                    self.signing_time.strftime("D:%Y%m%d%H%M%SZ")
                ),
            }
        )
        return signature_field_value

    def _register_signature_field(
        self,
        form: DictionaryObject,
        page: PageObject,
        signature_field_ref: IndirectObject,
    ) -> None:
        existing = form.get("/Fields")
        fields = existing.get_object() if existing is not None else None
        if not isinstance(fields, ArrayObject):
            fields = ArrayObject()
            form[NameObject("/Fields")] = fields
        fields.append(signature_field_ref)

        if "/Annots" not in page:
            page[NameObject("/Annots")] = ArrayObject()
        page[NameObject("/Annots")].append(signature_field_ref)

    def _setup_form(
        self,
        visible_signature: bool,
        field_name: str,
        signer: ResUsers | None = None,
    ) -> tuple[DictionaryObject, DictionaryObject]:
        form = self._acro_form()
        page = self.writer.pages[0]

        signature_field = DictionaryObject()
        signature_field.update(
            {
                NameObject("/FT"): NameObject("/Sig"),
                NameObject("/T"): create_string_object(field_name),
                NameObject("/Type"): NameObject("/Annot"),
                NameObject("/Subtype"): NameObject("/Widget"),
                NameObject("/F"): NumberObject(132),
                NameObject("/P"): page.indirect_reference,
            }
        )

        if visible_signature:
            rect, signature_appearence = self._visible_appearance(page, signer)
            signature_field.update({NameObject("/AP"): signature_appearence})
        else:
            rect = [0, 0, 0, 0]

        signature_field.update(
            {NameObject("/Rect"): self._create_number_array_object(rect)}
        )

        signature_field_value = self._signature_field_value()
        signature_field_ref = self.writer._add_object(signature_field)
        signature_field_value_ref = self.writer._add_object(signature_field_value)
        signature_field.update({NameObject("/V"): signature_field_value_ref})

        self._register_signature_field(form, page, signature_field_ref)
        return signature_field, signature_field_value

    def _get_signature_algorithm(
        self, private_key: PrivateKeyTypes
    ) -> _SignatureAlgorithm | None:
        if isinstance(private_key, rsa.RSAPrivateKey):
            return _SignatureAlgorithm(
                "sha256",
                "sha256_rsa",
                lambda data: private_key.sign(
                    data, padding.PKCS1v15(), hashes.SHA256()
                ),
            )
        if isinstance(private_key, ec.EllipticCurvePrivateKey):
            return _SignatureAlgorithm(
                "sha256",
                "sha256_ecdsa",
                lambda data: private_key.sign(data, ec.ECDSA(hashes.SHA256())),
            )
        if isinstance(private_key, ed25519.Ed25519PrivateKey):
            return _SignatureAlgorithm("sha512", "ed25519", private_key.sign)
        return None

    def _signed_attributes(
        self, digest: bytes, algorithm: _SignatureAlgorithm
    ) -> cms.CMSAttributes:
        return cms.CMSAttributes(
            [
                cms.CMSAttribute({"type": "content_type", "values": ["data"]}),
                cms.CMSAttribute(
                    {
                        "type": "signing_time",
                        "values": [
                            cms.Time({"utc_time": core.UTCTime(self.signing_time)})
                        ],
                    }
                ),
                cms.CMSAttribute(
                    {
                        "type": "cms_algorithm_protection",
                        "values": [
                            cms.CMSAlgorithmProtection(
                                {
                                    "mac_algorithm": None,
                                    "digest_algorithm": cms.DigestAlgorithm(
                                        {
                                            "algorithm": algorithm.digest,
                                            "parameters": None,
                                        }
                                    ),
                                    "signature_algorithm": cms.SignedDigestAlgorithm(
                                        {
                                            "algorithm": algorithm.signature,
                                            "parameters": None,
                                        }
                                    ),
                                }
                            )
                        ],
                    }
                ),
                cms.CMSAttribute({"type": "message_digest", "values": [digest]}),
            ]
        )

    @staticmethod
    def _signer_info(
        cert: x509.Certificate,
        attrs: cms.CMSAttributes,
        signature: bytes,
        algorithm: _SignatureAlgorithm,
    ) -> cms.SignerInfo:
        return cms.SignerInfo(
            {
                "version": "v1",
                "digest_algorithm": algos.DigestAlgorithm(
                    {"algorithm": algorithm.digest}
                ),
                "signature_algorithm": algos.SignedDigestAlgorithm(
                    {"algorithm": algorithm.signature}
                ),
                "signature": signature,
                "sid": cms.SignerIdentifier(
                    {
                        "issuer_and_serial_number": cms.IssuerAndSerialNumber(
                            {
                                "issuer": cert.issuer,
                                "serial_number": cert.serial_number,
                            }
                        )
                    }
                ),
                "signed_attrs": attrs,
            }
        )

    def _get_cms_object(
        self,
        digest: bytes,
        certificate: Certificate,
        algorithm: _SignatureAlgorithm,
    ) -> cms.ContentInfo:
        cert = x509.Certificate.load(certificate.public_bytes(encoding=Encoding.DER))
        attrs = self._signed_attributes(digest, algorithm)
        signer_info = self._signer_info(
            cert, attrs, algorithm.sign(attrs.dump()), algorithm
        )

        signed_data = {
            "version": "v1",
            "digest_algorithms": [
                algos.DigestAlgorithm({"algorithm": algorithm.digest})
            ],
            "encap_content_info": {"content_type": "data", "content": None},
            "certificates": [cert],
            "signer_infos": [signer_info],
        }

        return cms.ContentInfo(
            {
                "content_type": "signed_data",
                "content": cms.SignedData(signed_data),
            }
        )

    def _locate_contents_placeholder(
        self, pdf_data: bytes
    ) -> tuple[int, int, bytes] | None:
        signature_field_pos = pdf_data.rfind(b"/FT /Sig")
        if signature_field_pos == -1:
            _logger.warning(
                "Cannot sign PDF: no /FT /Sig field in the serialized document"
            )
            return None
        contents_field_pos = pdf_data.find(b"Contents", signature_field_pos)
        if contents_field_pos == -1:
            _logger.warning(
                "Cannot sign PDF: no /Contents entry after the signature field"
            )
            return None

        placeholder_start = contents_field_pos + 9
        placeholder_end = placeholder_start + self._CONTENTS_PLACEHOLDER_BYTES * 2 + 2
        placeholder = b"<" + b"0" * (self._CONTENTS_PLACEHOLDER_BYTES * 2) + b">"
        if pdf_data[placeholder_start:placeholder_end] != placeholder:
            _logger.warning(
                "Cannot sign PDF: /Contents placeholder not found at the "
                "computed offset"
            )
            return None
        return placeholder_start, placeholder_end, placeholder

    def _sign_field(self, sig_field_value: DictionaryObject) -> bool:
        private_key, certificate = self._load_key_and_certificate()
        if private_key is None or certificate is None:
            _debug.logic("pdf.signature_no_certificate")
            return False
        algorithm = self._get_signature_algorithm(private_key)
        _debug.logic(
            "pdf.signature_algorithm",
            key_type=type(private_key).__name__,
            algorithm=None if algorithm is None else algorithm.signature,
        )
        if algorithm is None:
            msg = (
                f"unsupported private key type {type(private_key).__name__} "
                "(supported: RSA, EC, Ed25519)"
            )
            _logger.warning("Cannot sign PDF: %s", msg)
            raise PdfSignatureError(msg)

        pdf_data = self._prepare_document_bytes()

        located = self._locate_contents_placeholder(pdf_data)
        if located is None:
            _debug.logic("pdf.signature_placeholder_missing", size=len(pdf_data))
            msg = "could not locate a valid /Contents placeholder to sign"
            raise PdfSignatureError(msg)
        placeholder_start, placeholder_end, placeholder = located

        placeholder_byte_range = sig_field_value.get("/ByteRange")

        byte_range = [
            0,
            placeholder_start,
            placeholder_end,
            abs(len(pdf_data) - placeholder_end),
        ]

        byte_range = self._correct_byte_range(
            placeholder_byte_range, byte_range, len(pdf_data)
        )

        sig_field_value.update(
            {NameObject("/ByteRange"): self._create_number_array_object(byte_range)}
        )

        pdf_data = self._prepare_document_bytes()

        if pdf_data[placeholder_start:placeholder_end] != placeholder:
            msg = (
                f"filling in /ByteRange moved the /Contents placeholder "
                f"(expected it at {placeholder_start}..{placeholder_end}), so "
                "the digest would cover the wrong bytes. /Contents must "
                "serialise before /ByteRange."
            )
            _logger.error("Cannot sign PDF: %s", msg)
            raise PdfSignatureError(msg)

        digest = self._compute_digest_from_byte_range(
            pdf_data, byte_range, algorithm.digest
        )

        cms_content_info = self._get_cms_object(digest, certificate, algorithm)

        signature_der = cms_content_info.dump()
        _debug.logic(
            "pdf.signature_cms",
            signature_bytes=len(signature_der),
            reserved=self._CONTENTS_PLACEHOLDER_BYTES,
            byte_range=byte_range,
        )
        if len(signature_der) > self._CONTENTS_PLACEHOLDER_BYTES:
            raise ValueError(
                f"PDF signature ({len(signature_der)} bytes) exceeds the reserved "
                f"{self._CONTENTS_PLACEHOLDER_BYTES} bytes; the certificate is too large to embed."
            )
        signature_hex = signature_der.hex().ljust(
            self._CONTENTS_PLACEHOLDER_BYTES * 2, "0"
        )

        sig_field_value.update(
            {NameObject("/Contents"): ByteStringObject(bytes.fromhex(signature_hex))}
        )
        return True

    def _prepare_document_bytes(self) -> bytes:
        output_stream = io.BytesIO()
        self.writer.write_stream(output_stream)
        return output_stream.getvalue()

    def _correct_byte_range(
        self, old_range: list[int], new_range: list[int], base_pdf_len: int
    ) -> list[int]:
        current_len = len(str(old_range))
        corrected_len = len(str(new_range))
        diff = corrected_len - current_len

        if diff == 0:
            return new_range

        corrected_range = new_range.copy()
        corrected_range[-1] = abs((base_pdf_len + diff) - new_range[-2])
        return self._correct_byte_range(new_range, corrected_range, base_pdf_len)

    def _compute_digest_from_byte_range(
        self, data: bytes, byte_range: list[int], algorithm: str = "sha256"
    ) -> bytes:
        hashed = hashlib.new(algorithm)
        for i in range(0, len(byte_range), 2):
            hashed.update(data[byte_range[i] : byte_range[i] + byte_range[i + 1]])
        return hashed.digest()

    def _create_number_array_object(self, array: Sequence[float]) -> ArrayObject:
        return ArrayObject([NumberObject(item) for item in array])


_BYTE_RANGE_RE = re.compile(rb"/ByteRange\s*\[\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*\]")
_CONTENTS_RE = re.compile(rb"<([0-9A-Fa-f]*)>")
_DIGESTS = frozenset(("sha256", "sha384", "sha512"))
_MAX_CHAIN = 8


class VerifiedPdfSignature(NamedTuple):
    signer: Certificate
    contents_offset: int


def get_verified_pdf_signature(
    data: bytes,
    trust_roots: Sequence[Certificate],
    moment: datetime.datetime,
) -> VerifiedPdfSignature:
    if not HAS_CRYPTOGRAPHY:
        raise PdfSignatureError("cryptography is not installed")
    ranges = list(_BYTE_RANGE_RE.finditer(data))
    if not ranges:
        raise PdfSignatureError("the document carries no signature")
    start, gap_start, gap_end, tail = (int(group) for group in ranges[-1].groups())
    if start != 0 or not 0 < gap_start < gap_end or gap_end + tail != len(data):
        raise PdfSignatureError("the last signature does not cover the whole document")
    contents = _CONTENTS_RE.fullmatch(data[gap_start:gap_end])
    if contents is None:
        raise PdfSignatureError("the signature's /Contents is not a hex string")
    try:
        content_info = cms.ContentInfo.load(bytes.fromhex(contents.group(1).decode()))
        if content_info["content_type"].native != "signed_data":
            raise PdfSignatureError("the signature is not CMS signed data")
        signed_data = content_info["content"]
        (signer_info,) = signed_data["signer_infos"]
        certificates = [
            load_der_x509_certificate(choice.chosen.dump())
            for choice in signed_data["certificates"] or ()
            if choice.name == "certificate"
        ]
        attributes = signer_info["signed_attrs"]
        values = {attr["type"].native: attr["values"] for attr in attributes}
        digest_name = signer_info["digest_algorithm"]["algorithm"].native
        algorithm = signer_info["signature_algorithm"]
        signature = signer_info["signature"].native
        signer = _signer_certificate(signer_info["sid"], certificates)
    except (ValueError, TypeError, KeyError) as e:
        raise PdfSignatureError(f"the signature cannot be read: {e}") from e
    if digest_name not in _DIGESTS:
        raise PdfSignatureError(f"digest {digest_name} is not accepted")
    if [value.native for value in values.get("content_type", ())] != ["data"]:
        raise PdfSignatureError("the signed attributes do not declare data")
    declared = [value.native for value in values.get("message_digest", ())]
    covered = hashlib.new(digest_name, data[:gap_start] + data[gap_end:]).digest()
    if len(declared) != 1 or not hmac.compare_digest(declared[0], covered):
        raise PdfSignatureError("the signature does not describe these bytes")
    tagged = bytearray(attributes.dump())
    tagged[0] = 0x31
    _check_signature(signer, algorithm, digest_name, signature, bytes(tagged))
    _check_certificate_chain(signer, certificates, trust_roots, moment)
    return VerifiedPdfSignature(signer, gap_start)


def _signer_certificate(
    sid: cms.SignerIdentifier, certificates: Sequence[Certificate]
) -> Certificate:
    if sid.name == "issuer_and_serial_number":
        issuer = sid.chosen["issuer"].dump()
        serial = sid.chosen["serial_number"].native
        for certificate in certificates:
            if (
                certificate.serial_number == serial
                and certificate.issuer.public_bytes() == issuer
            ):
                return certificate
    else:
        key_identifier = sid.chosen.native
        for certificate in certificates:
            try:
                extension = certificate.extensions.get_extension_for_class(
                    SubjectKeyIdentifier
                )
            except ExtensionNotFound:
                continue
            if extension.value.digest == key_identifier:
                return certificate
    raise PdfSignatureError("the signer's certificate is not in the signature")


def _check_signature(
    certificate: Certificate,
    algorithm: algos.SignedDigestAlgorithm,
    digest_name: str,
    signature: bytes,
    payload: bytes,
) -> None:
    digest = getattr(hashes, digest_name.upper())()
    public_key = certificate.public_key()
    scheme = algorithm.signature_algo
    try:
        if scheme == "rsassa_pkcs1v15" and isinstance(public_key, rsa.RSAPublicKey):
            public_key.verify(signature, payload, padding.PKCS1v15(), digest)
        elif scheme == "rsassa_pss" and isinstance(public_key, rsa.RSAPublicKey):
            parameters = algorithm["parameters"]
            pss_digest = getattr(
                hashes, parameters["hash_algorithm"]["algorithm"].native.upper()
            )()
            mgf_digest = getattr(
                hashes,
                parameters["mask_gen_algorithm"]["parameters"][
                    "algorithm"
                ].native.upper(),
            )()
            public_key.verify(
                signature,
                payload,
                padding.PSS(padding.MGF1(mgf_digest), parameters["salt_length"].native),
                pss_digest,
            )
        elif scheme == "ecdsa" and isinstance(public_key, ec.EllipticCurvePublicKey):
            public_key.verify(signature, payload, ec.ECDSA(digest))
        elif scheme == "ed25519" and isinstance(public_key, ed25519.Ed25519PublicKey):
            public_key.verify(signature, payload)
        else:
            raise PdfSignatureError(f"signature scheme {scheme} is not accepted")
    except InvalidSignature as e:
        raise PdfSignatureError("the signature does not verify") from e


def _check_certificate_chain(
    leaf: Certificate,
    pool: Sequence[Certificate],
    trust_roots: Sequence[Certificate],
    moment: datetime.datetime,
) -> None:
    _check_usage(leaf)
    current = leaf
    for _depth in range(_MAX_CHAIN):
        _check_validity(current, moment)
        for root in trust_roots:
            if root.subject == current.issuer and _issued_by(current, root):
                _check_validity(root, moment)
                return
        issuer = next(
            (
                candidate
                for candidate in pool
                if candidate.subject == current.issuer
                and candidate != current
                and _is_ca(candidate)
                and _issued_by(current, candidate)
            ),
            None,
        )
        if issuer is None:
            break
        current = issuer
    raise PdfSignatureError("the signer's certificate does not chain to a trusted root")


def _issued_by(certificate: Certificate, issuer: Certificate) -> bool:
    try:
        certificate.verify_directly_issued_by(issuer)
    except ValueError, TypeError, InvalidSignature:
        return False
    return True


def _is_ca(certificate: Certificate) -> bool:
    try:
        return certificate.extensions.get_extension_for_class(BasicConstraints).value.ca
    except ExtensionNotFound:
        return False


def _check_usage(leaf: Certificate) -> None:
    if _is_ca(leaf):
        raise PdfSignatureError("the signer's certificate is a CA certificate")
    try:
        usage = leaf.extensions.get_extension_for_class(KeyUsage).value
    except ExtensionNotFound:
        return
    if not (usage.digital_signature or usage.content_commitment):
        raise PdfSignatureError("the signer's certificate may not sign documents")


def _check_validity(certificate: Certificate, moment: datetime.datetime) -> None:
    if not (
        certificate.not_valid_before_utc <= moment <= certificate.not_valid_after_utc
    ):
        raise PdfSignatureError(
            f"certificate {certificate.subject.rfc4514_string()} is not valid at {moment}"
        )
