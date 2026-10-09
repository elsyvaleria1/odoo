{
    "name": "Passkey Proof of Identity",
    "version": "19.0.1.0.0",
    "category": "Hidden",
    "summary": "Let users prove an act they vouch for with one of their own passkeys, user verification required",
    "description": "Adds the Passkey proof method. The passkey signs a WebAuthn challenge derived from the proof challenge's one-time token and its digest of the record's figures, so the signature covers those figures. Only the user's own passkeys are offered and accepted, with user verification (fingerprint, face or device PIN) required and the sign count advanced. The evidence keeps the signed authenticator data, client data, signature and public key, so the signature can be checked again later. Requires a browser and authenticator supporting WebAuthn and a correctly configured site URL, as passkey login does.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "LGPL-3",
    "depends": [
        "auth_passkey",
        "proof",
    ],
    "data": [
        "data/proof_method_data.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "auth_passkey_proof/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "auth_passkey_proof/static/tests/**/*",
        ],
    },
    "auto_install": True,
}
