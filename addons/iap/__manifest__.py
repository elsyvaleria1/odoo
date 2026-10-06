{
    "name": "In-App Service Accounts",
    "version": "1.2",
    "oldest_upgradable_version": "1.2",
    "category": "Hidden/Tools",
    "summary": "Manage service accounts and credit access for consuming addons",
    "description": "Adds service definitions, credential-backed account tokens, account configuration and remote credit-balance or purchase links, plus service-request helpers. Consumer addons implement their specific paid features; balances and service availability depend on the external IAP endpoint and account.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "web",
        "credential",
    ],
    "data": [
        "data/services.xml",
        "security/ir.access.csv",
        "views/iap_views.xml",
        "views/res_config_settings.xml",
        "views/iap_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "iap/static/src/**/*.js",
            "iap/static/src/**/*.xml",
        ],
    },
    "auto_install": True,
}
