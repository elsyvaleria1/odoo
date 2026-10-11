{
    "name": "Twilio Integration",
    "version": "19.0.2.0.0",
    "oldest_upgradable_version": "1.4",
    "category": "Hidden/Tools",
    "summary": "Connect each company's Twilio account for SMS delivery, inbound SMS conversations and account checks",
    "description": "Keeps one Twilio account per company in the credential vault and sends every Twilio API call through the integration transport. Sends SMS through the account when the company selects Twilio as its SMS provider, records delivery status from signed callbacks, and turns SMS received on the company's Twilio numbers into one Discuss conversation per sender, whose replies are sent back as SMS from the same number. Syncs the account's numbers and their capabilities and can point a number's incoming-SMS webhook at Odoo. Requires a Twilio Account SID and Auth Token, numbers able to send and receive SMS, and a public HTTPS base URL for Twilio's webhooks.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "Other OSI approved licence",
    "depends": [
        "credential",
        "integration",
        "phone_call",
        "sms",
    ],
    "data": [
        "data/integration_service_data.xml",
        "security/integration_twilio_security.xml",
        "security/ir.access.csv",
        "data/ir_cron_data.xml",
        "data/mail_activity_type_data.xml",
        "views/integration_twilio_call_views.xml",
        "views/integration_twilio_menus.xml",
        "views/sms_sms_views.xml",
        "wizards/res_config_settings_views.xml",
        "wizards/wizard_integration_twilio_config_update_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "integration_twilio/static/src/core/public_web/**/*",
        ],
        "web.assets_unit_tests": [
            "integration_twilio/static/tests/**/*",
        ],
    },
    "pre_init_hook": "pre_init_hook",
    "uninstall_hook": "uninstall_hook",
}
