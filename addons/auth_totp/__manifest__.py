{
    "name": "Two-Factor Authentication (TOTP)",
    "version": "1.4",
    "oldest_upgradable_version": "1.3",
    "category": "Hidden/Tools",
    "summary": "Require time-based one-time passwords for enrolled user accounts",
    "description": """
Two-Factor Authentication (TOTP)
================================
Allows users to configure two-factor authentication on their user account
for extra security, using time-based one-time passwords (TOTP).

Once enabled, the user will need to enter a 6-digit code as provided
by their authenticator app before being granted access to the system.
All popular authenticator apps are supported.

Note: logically, two-factor prevents password-based RPC access for users
where it is enabled. In order to be able to execute RPC scripts, the user
can setup API keys to replace their main password.
    """,
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "web",
    ],
    "external_dependencies": {
        "python": [
            "qrcode",
        ],
        "apt": {
            "qrcode": "python3-qrcode",
        },
    },
    "data": [
        "security/ir.access.csv",
        "data/ir_action_data.xml",
        "views/auth_user_client_views.xml",
        "views/res_users_views.xml",
        "views/templates.xml",
        "wizards/wizard_res_users_enable_totp_views.xml",
    ],
    "assets": {
        "web.assets_tests": [
            "auth_totp/static/tests/**/*",
        ],
        "web.assets_backend": [
            "auth_totp/static/src/**/*",
        ],
    },
    "auto_install": True,
}
