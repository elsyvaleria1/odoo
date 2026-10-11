{
    "name": "Browser VoIP Calling",
    "version": "2.3",
    "oldest_upgradable_version": "2.2",
    "category": "Productivity/Phone",
    "sequence": 280,
    "summary": "Make and receive calls through a configured VoIP provider and record call activity",
    "description": "Adds a browser softphone, provider and user credentials, call history and activity queues. Requires a compatible SIP provider, its connection settings and browser media permissions; installing the addon alone does not supply a telephone service or phone number.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "credential",
        "base",
        "bus",
        "mail",
        "phone_call",
        "phone_validation",
        "web",
        "web_mobile",
    ],
    "data": [
        "security/voip_security.xml",
        "data/voip_data.xml",
        "security/ir.access.csv",
        "views/voip_provider_views.xml",
        "views/phone_call_views.xml",
        "views/res_users_views.xml",
        "views/res_users_settings_views.xml",
        "views/res_config_settings_views.xml",
        "views/voip_menu_views.xml",
    ],
    "demo": [
        "demo/res_groups.xml",
    ],
    "assets": {
        "voip.assets_sip": [
            "voip/static/lib/sip.js",
        ],
        "web.assets_backend": [
            "voip/static/src/**/*",
            (
                "remove",
                "voip/static/src/worker/**/*",
            ),
        ],
        "voip.assets_public": [
            "mail/static/src/core/common/**/*",
        ],
        "web.assets_web_dark": [],
        "web.assets_unit_tests": [
            "voip/static/tests/**/*",
            "voip/static/src/worker/*",
            (
                "remove",
                "voip/static/src/worker/init.js",
            ),
        ],
        "bus.websocket_worker_assets": [
            "voip/static/src/worker/*",
        ],
    },
    "application": True,
}
