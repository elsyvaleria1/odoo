{
    "name": "User Signup and Password Reset",
    "version": "1.0",
    "category": "Hidden/Tools",
    "summary": "Register user accounts and handle password-reset invitations",
    "description": "Provide signup, invitation and password-reset routes and token handling. Availability follows the configured signup policy and account invitation state.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "mail",
    ],
    "data": [
        "data/ir_config_parameter_data.xml",
        "data/ir_cron_data.xml",
        "data/mail_template_data.xml",
        "views/res_config_settings_views.xml",
        "views/res_users_views.xml",
        "views/auth_signup_login_templates.xml",
        "views/auth_signup_templates_email.xml",
        "views/webclient_templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "auth_signup/static/**/*",
        ],
    },
    "bootstrap": True,
    "auto_install": True,
}
