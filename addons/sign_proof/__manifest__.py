{
    "name": "Sign: Signer Proves It Is Them With a Code",
    "version": "19.0.1.0.0",
    "category": "Sales/Sign",
    "summary": "A signer proves it is them with a one-time code sent to their own email or Telegram before their signature is taken",
    "description": "Adds an authentication method to signing roles: before the signature is submitted, the signer has a one-time code sent to every channel of theirs a proof method reaches (email, Telegram) and types it in. The code proves them through whoever sent the request, as a contact proves through the user who asks them, and covers the request, the signer and the documents as sent: it is kept as chained proof evidence, its hash goes into the signature's log entry, and the certificate of completion says where the code went. It works the same on the signer's own device and when the requester has each signer sign on theirs.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "LGPL-3",
    "depends": [
        "proof",
        "sign",
    ],
    "data": [
        "reports/sign_log_reports.xml",
    ],
    "assets": {
        "sign.assets_public_sign": [
            "sign_proof/static/src/**/*",
        ],
        "web.assets_backend": [
            "sign_proof/static/src/**/*",
        ],
        "web.assets_frontend": [
            "sign_proof/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "sign_proof/static/tests/**/*",
        ],
    },
}
