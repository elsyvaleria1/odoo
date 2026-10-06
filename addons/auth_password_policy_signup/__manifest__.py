{
    "name": "Signup Password Policy",
    "category": "Hidden/Tools",
    "summary": "Expose password-policy settings on signup and password-reset pages",
    "description": "Extend signup configuration with password-policy requirements. Provides frontend assets and translations for password entry guidance.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "auth_password_policy",
        "auth_signup",
    ],
    "data": [
        "views/signup_templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "auth_password_policy_signup/static/src/public/**/*",
            "auth_password_policy/static/src/password_meter.js",
            "auth_password_policy/static/src/password_policy.js",
        ],
    },
    "auto_install": True,
}
