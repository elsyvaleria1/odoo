import base64
import hashlib
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from odoo.tests import TransactionCase, tagged

from odoo.addons.certificate.models.certificate_certificate import (
    _parse_x509_certificate,
)


@tagged("post_install", "-at_install")
class TestCertificateBytesAndLifecycle(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = x509.Name(
            [x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, "cert-bytes-test")],
        )
        issuer = x509.Name(
            [
                x509.NameAttribute(x509.oid.NameOID.COUNTRY_NAME, "EC"),
                x509.NameAttribute(x509.oid.NameOID.ORGANIZATION_NAME, "Issuer, Inc."),
                x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, "Signing Authority"),
            ]
        )
        now = datetime.now(UTC)
        cls.crypto_cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(cls.private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=30))
            .sign(cls.private_key, hashes.SHA256())
        )
        cls.certificate = cls.env["certificate.certificate"].create(
            {
                "name": "Bytes test certificate",
                "content": base64.b64encode(
                    cls.crypto_cert.public_bytes(serialization.Encoding.PEM)
                ),
            },
        )

    def test_der_and_fingerprint_bytes_round_trip(self):
        der_raw = self.certificate._get_der_certificate_bytes(formatting="raw")
        reloaded = x509.load_der_x509_certificate(der_raw)
        common_names = reloaded.subject.get_attributes_for_oid(
            x509.oid.NameOID.COMMON_NAME
        )
        self.assertEqual(common_names[0].value, "cert-bytes-test")

        fingerprint = self.certificate._get_fingerprint_bytes(formatting="raw")
        self.assertEqual(fingerprint, hashlib.sha256(der_raw).digest())

    def test_issuer_rfc4514_name(self):
        expected = r"CN=Signing Authority,O=Issuer\, Inc.,C=EC"
        self.assertEqual(self.certificate._get_issuer_rfc4514_name(), expected)
        self.assertEqual(
            self.certificate.with_context(bin_size=True)._get_issuer_rfc4514_name(),
            expected,
        )

    def test_issuer_reuses_parsed_certificate(self):
        _parse_x509_certificate.cache_clear()
        self.addCleanup(_parse_x509_certificate.cache_clear)
        with patch.object(
            x509, "load_pem_x509_certificate", wraps=x509.load_pem_x509_certificate
        ) as parse:
            self.certificate._get_issuer_rfc4514_name()
            self.certificate._get_der_certificate_bytes()
            self.certificate._get_fingerprint_bytes()
        self.assertEqual(parse.call_count, 1)

    def test_issuer_requires_singleton(self):
        certificates = self.env["certificate.certificate"]
        with self.assertRaises(ValueError):
            certificates._get_issuer_rfc4514_name()
        with self.assertRaises(ValueError):
            (self.certificate + self.certificate.copy())._get_issuer_rfc4514_name()

    def test_signature_and_public_numbers_bytes(self):
        signature = base64.b64decode(
            self.certificate._get_signature_bytes(formatting="base64")
        )
        self.assertEqual(signature, self.crypto_cert.signature)

        e_bytes, _n_bytes = self.certificate._get_public_key_numbers_bytes(
            formatting="base64"
        )
        self.assertEqual(int.from_bytes(base64.b64decode(e_bytes)), 65537)

    def test_cleared_content_resets_computed_fields(self):
        certificate = self.env["certificate.certificate"].create(
            {
                "name": "To clear",
                "content": base64.b64encode(
                    self.crypto_cert.public_bytes(serialization.Encoding.PEM)
                ),
            },
        )
        self.assertTrue(certificate.pem_certificate)

        certificate.content = False

        self.assertFalse(certificate.pem_certificate)
        self.assertFalse(certificate.serial_number)
        self.assertFalse(certificate.is_valid)
        self.assertFalse(certificate.loading_error)

    def test_garbage_content_sets_loading_error(self):
        certificate = self.env["certificate.certificate"].create(
            {
                "name": "Garbage",
                "content": base64.b64encode(b"this is not a certificate"),
            },
        )
        self.assertTrue(certificate.loading_error)
        self.assertFalse(certificate.pem_certificate)
        self.assertFalse(certificate.is_valid)

    def test_search_is_valid_domain(self):
        garbage = self.env["certificate.certificate"].create(
            {
                "name": "Search garbage",
                "content": base64.b64encode(b"still not a certificate"),
            },
        )
        found = self.env["certificate.certificate"].search([("is_valid", "=", True)])
        self.assertIn(self.certificate, found)
        self.assertNotIn(garbage, found)

    def test_search_is_valid_unsupported_operator(self):
        result = self.env["certificate.certificate"]._search_is_valid("child_of", True)
        self.assertIs(result, NotImplemented)
