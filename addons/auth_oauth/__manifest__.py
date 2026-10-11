{
    "name": "OAuth Authentication",
    "version": "1.2",
    "oldest_upgradable_version": "1.2",
    "category": "Hidden/Tools",
    "summary": "Sign users in through configured OAuth providers",
    "description": "Add provider selection and callback processing to the login flow. Requires provider configuration and maps the returned identity to an application user.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "auth_signup",
    ],
    "data": [
        "data/auth_oauth_data.xml",
        "views/auth_oauth_views.xml",
        "views/res_config_settings_views.xml",
        "views/auth_oauth_templates.xml",
        "security/ir.access.csv",
        "views/auth_oauth_menus.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "auth_oauth/static/**/*",
        ],
    },
}
