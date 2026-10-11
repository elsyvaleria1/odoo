{
    "name": "OnSIP Phone Connection",
    "version": "1.0",
    "category": "Productivity/Phone",
    "summary": "Configure OnSIP authentication for the phone client",
    "description": "Add OnSIP provider options and authentication usernames to user phone configuration. Requires an OnSIP account and its connection credentials.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "voip",
    ],
    "data": [
        "views/res_users_views.xml",
        "views/voip_provider_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "voip_onsip/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "voip_onsip/static/tests/**/*",
        ],
    },
}
