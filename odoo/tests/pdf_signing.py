from __future__ import annotations

import datetime
import io
from typing import TYPE_CHECKING, NamedTuple, cast, override

from asn1crypto import x509 as asn1_x509
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509.oid import NameOID

from odoo.tools.pdf import PdfWriter
from odoo.tools.pdf.signature import PdfSigner

if TYPE_CHECKING:
    from asn1crypto import cms
    from cryptography.hazmat.primitives.asymmetric.types import PrivateKeyTypes

    from odoo.tools.pdf.signature import _SignatureAlgorithm

    from odoo.addons.base.models.res_company import ResCompany

_START = datetime.datetime(2020, 1, 1, tzinfo=datetime.UTC)
_END = datetime.datetime(2040, 1, 1, tzinfo=datetime.UTC)


class SigningPki(NamedTuple):
    root: x509.Certificate
    intermediate: x509.Certificate
    leaf: x509.Certificate
    leaf_key: rsa.RSAPrivateKey


def _name(common_name: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])


def _certificate(
    subject: str,
    key: rsa.RSAPrivateKey,
    issuer: str,
    issuer_key: rsa.RSAPrivateKey,
    ca: bool,
    not_before: datetime.datetime,
    not_after: datetime.datetime,
) -> x509.Certificate:
    return (
        x509.CertificateBuilder()
        .subject_name(_name(subject))
        .issuer_name(_name(issuer))
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
        .sign(issuer_key, hashes.SHA256())
    )


def make_signing_pki(
    signer_name: str = "Test Signer",
    not_before: datetime.datetime = _START,
    not_after: datetime.datetime = _END,
) -> SigningPki:
    root_key, intermediate_key, leaf_key = (
        rsa.generate_private_key(public_exponent=65537, key_size=2048)
        for _key in range(3)
    )
    root = _certificate(
        "Test Root", root_key, "Test Root", root_key, True, _START, _END
    )
    intermediate = _certificate(
        "Test Sub CA", intermediate_key, "Test Root", root_key, True, _START, _END
    )
    leaf = _certificate(
        signer_name,
        leaf_key,
        "Test Sub CA",
        intermediate_key,
        False,
        not_before,
        not_after,
    )
    return SigningPki(root, intermediate, leaf, leaf_key)


class _IncrementalSigner(PdfSigner):
    def __init__(
        self, pdf: bytes, pki: SigningPki, signing_time: datetime.datetime | None
    ) -> None:
        super().__init__(
            io.BytesIO(pdf),
            company=cast("ResCompany", object()),
            signing_time=signing_time,
        )
        self.writer = PdfWriter(io.BytesIO(pdf), incremental=True)
        self.pki = pki

    @override
    def _load_key_and_certificate(
        self,
    ) -> tuple[PrivateKeyTypes | None, x509.Certificate | None]:
        return self.pki.leaf_key, self.pki.leaf

    @override
    def _get_cms_object(
        self,
        digest: bytes,
        certificate: x509.Certificate,
        algorithm: _SignatureAlgorithm,
    ) -> cms.ContentInfo:
        content_info = super()._get_cms_object(digest, certificate, algorithm)
        signed_data = content_info["content"]
        signed_data["certificates"] = [
            *signed_data["certificates"],
            asn1_x509.Certificate.load(
                self.pki.intermediate.public_bytes(Encoding.DER)
            ),
        ]
        return content_info


def sign_incrementally(
    pdf: bytes, pki: SigningPki, signing_time: datetime.datetime | None = None
) -> bytes:
    signed = _IncrementalSigner(pdf, pki, signing_time).sign_pdf()
    if signed is None:
        raise AssertionError("the test signer refused to sign")
    return signed.getvalue()
