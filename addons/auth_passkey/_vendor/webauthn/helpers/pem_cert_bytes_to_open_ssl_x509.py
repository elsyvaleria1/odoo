from cryptography.x509 import load_pem_x509_certificate
from OpenSSL.crypto import X509


def pem_cert_bytes_to_open_ssl_x509(cert: bytes) -> X509:
    cert_crypto = load_pem_x509_certificate(cert)
    cert_openssl = X509().from_cryptography(cert_crypto)
    return cert_openssl
