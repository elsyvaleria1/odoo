{
    "name": "Twilio SMS Delivery",
    "version": "1.4",
    "oldest_upgradable_version": "1.4",
    "category": "Hidden/Tools",
    "summary": "Send SMS through configured Twilio accounts and process delivery updates",
    "description": "Adds company provider selection, account and sender-number setup, test sending and delivery-status handling to SMS. Requires Twilio credentials and an eligible sender configuration. The default provider remains Odoo until Twilio is selected; message acceptance and delivery depend on provider service and account eligibility.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "credential",
        "integration",
        "sms",
    ],
    "data": [
        "views/res_config_settings_views.xml",
        "views/sms_sms_views.xml",
        "wizards/wizard_sms_twilio_config_update_views.xml",
        "security/ir.access.csv",
    ],
}
