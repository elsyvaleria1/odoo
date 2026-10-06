{
    "name": "Mobile Message Notifications",
    "version": "1.2",
    "oldest_upgradable_version": "1.2",
    "category": "Hidden/Tools",
    "summary": "Deliver message push notifications to registered mobile devices",
    "description": "Registers mobile devices and sends messaging notification payloads through the configured notification service. Adds mobile back-button handling for messaging views; notification delivery requires a registered compatible client and service access.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "iap_mail",
        "mail",
        "web_mobile",
    ],
    "data": [
        "data/mail_mobile_data.xml",
        "views/res_config_settings_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "mail_mobile/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "mail_mobile/static/tests/**/*",
        ],
    },
    "auto_install": [
        "web_mobile",
        "mail",
    ],
}
