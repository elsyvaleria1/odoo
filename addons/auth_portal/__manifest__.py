{
    "name": "Portal Account Security",
    "version": "1.2",
    "category": "Hidden/Tools",
    "summary": "Manage two-factor authentication and passkeys from the portal account page",
    "description": "Adds portal controls for enabling or disabling two-factor authentication, revoking trusted devices and adding, renaming or deleting passkeys. Uses the authentication dependencies for credential operations; passkey enrollment requires a compatible browser and authenticator.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "portal",
        "auth_totp",
        "auth_totp_mail",
        "auth_passkey",
    ],
    "data": [
        "security/ir.access.csv",
        "views/templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "auth_portal/static/src/**/*",
        ],
        "web.assets_tests": [
            "auth_portal/static/tests/tours/**/*",
        ],
        "web.assets_unit_tests_setup": [
            "auth_passkey/static/lib/simplewebauthn.js",
            "auth_passkey/static/src/passkey_lib.js",
            "auth_portal/static/src/interactions/**/*",
            "auth_portal/static/src/xml/**/*",
        ],
        "web.assets_unit_tests": [
            "auth_portal/static/tests/**/*.test.js",
        ],
    },
    "auto_install": True,
}
