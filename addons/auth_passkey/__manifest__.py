{
    "name": "Passkey Authentication",
    "version": "1.2",
    "oldest_upgradable_version": "1.2",
    "category": "Hidden/Tools",
    "summary": "Register passkeys and authenticate users through WebAuthn",
    "description": "Adds passkey registration, credential management and browser login backed by WebAuthn challenge and origin verification. Requires a compatible browser and authenticator and a correctly configured site URL. Successful passkey authentication skips the separate MFA step in this implementation.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "web",
    ],
    "external_dependencies": {
        "python": [
            "cbor2",
        ],
    },
    "data": [
        "views/auth_passkey_key_views.xml",
        "views/auth_passkey_login_templates.xml",
        "wizards/wizard_res_users_check_identity_views.xml",
        "views/res_users_views.xml",
        "security/ir.access.csv",
    ],
    "assets": {
        "web.assets_backend": [
            "auth_passkey/static/lib/simplewebauthn.js",
            "auth_passkey/static/src/passkey_lib.js",
            "auth_passkey/static/src/views/*",
            "auth_passkey/static/src/scss/res_users.scss",
        ],
        "web.assets_frontend": [
            "auth_passkey/static/lib/simplewebauthn.js",
            "auth_passkey/static/src/passkey_lib.js",
            "auth_passkey/static/src/interactions/*",
        ],
        "web.assets_tests": [
            "auth_passkey/static/tests/*.js",
        ],
    },
    "auto_install": True,
}
