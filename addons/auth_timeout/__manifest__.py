{
    "name": "Session Identity Timeouts",
    "category": "Hidden/Tools",
    "summary": "Request identity verification after configured time or inactivity limits",
    "description": "Adds group-level timeout settings and session checks for password and multifactor reauthentication. The effective limits depend on the user groups and available authentication methods.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "auth_totp",
        "auth_totp_mail",
        "auth_passkey",
        "bus",
    ],
    "data": [
        "views/login_templates.xml",
        "views/res_groups_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "auth_timeout/static/src/services/check_identity/*",
        ],
        "web.assets_frontend": [
            "auth_timeout/static/src/services/check_identity/*",
            "auth_timeout/static/src/scss/auth_timeout.scss",
        ],
        "web.assets_tests": [
            "auth_timeout/static/tests/tours/**/*",
        ],
        "web.assets_unit_tests": [
            "auth_timeout/static/tests/**/*.test.js",
        ],
    },
}
