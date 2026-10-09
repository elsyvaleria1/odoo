{
    "name": "Email Code Proof of Identity",
    "version": "19.0.1.0.0",
    "category": "Hidden",
    "summary": "Let a user or a contact prove an act they vouch for with a one-time code sent to their own email",
    "description": "Adds the Email Code proof method. Asking for the proof sends a six-digit code to the signer's email, with what they are agreeing to; the signer reads it out or types it in, and the user who asked enters it. It works for users and for contacts with no user account, such as an outside custodian receiving a document, through the user who asks them. The challenge keeps only an HMAC of the code, under the database secret; five wrong codes spend it, counted outside the request so a refused code still counts; the code lives as long as the challenge. The evidence records the masked address the code went to. It proves possession of that mailbox, not of a key: categories that need more choose a passkey. The mail is sent at once and deleted once sent, so outgoing mail must be configured.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "LGPL-3",
    "depends": [
        "mail",
        "proof",
    ],
    "data": [
        "security/mail_proof_security.xml",
        "security/ir.access.csv",
        "data/proof_method_data.xml",
        "views/mail_proof_templates.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "mail_proof/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "mail_proof/static/tests/**/*",
        ],
    },
    "auto_install": True,
}
