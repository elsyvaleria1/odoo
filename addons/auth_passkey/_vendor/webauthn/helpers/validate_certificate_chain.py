from typing import List, Optional

from cryptography.x509 import load_der_x509_certificate
from OpenSSL.crypto import X509, X509Store, X509StoreContext, X509StoreContextError

from .exceptions import InvalidCertificateChain
from .pem_cert_bytes_to_open_ssl_x509 import pem_cert_bytes_to_open_ssl_x509


def validate_certificate_chain(
    *,
    x5c: List[bytes],
    pem_root_certs_bytes: Optional[List[bytes]] = None,
) -> bool:
    if pem_root_certs_bytes is None or len(pem_root_certs_bytes) < 1:
        return True

    if len(x5c) < 1:
        raise InvalidCertificateChain("x5c was empty")

    try:
        leaf_cert_bytes = x5c[0]
        leaf_cert_crypto = load_der_x509_certificate(leaf_cert_bytes)
        leaf_cert = X509().from_cryptography(leaf_cert_crypto)
    except Exception as err:
        raise InvalidCertificateChain(f"Could not prepare leaf cert: {err}")

    try:
        intermediate_certs_bytes = x5c[1:]
        intermediate_certs_crypto = [
            load_der_x509_certificate(cert) for cert in intermediate_certs_bytes
        ]
        intermediate_certs = [X509().from_cryptography(cert) for cert in intermediate_certs_crypto]
    except Exception as err:
        raise InvalidCertificateChain(f"Could not prepare intermediate certs: {err}")

    root_certs_store = X509Store()
    try:
        for cert in pem_root_certs_bytes:
            root_certs_store.add_cert(pem_cert_bytes_to_open_ssl_x509(cert))
    except Exception as err:
        raise InvalidCertificateChain(f"Could not prepare root certs: {err}")

    context = X509StoreContext(
        store=root_certs_store,
        certificate=leaf_cert,
        chain=intermediate_certs,
    )

    try:
        context.verify_certificate()
    except X509StoreContextError:
        raise InvalidCertificateChain("Certificate chain could not be validated")

    return True
