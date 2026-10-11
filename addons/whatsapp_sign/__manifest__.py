{
    "name": "WhatsApp Signature Request Messages",
    "category": "Productivity/WhatsApp",
    "summary": "Send signature request links and status messages through configured WhatsApp templates",
    "description": "Adds WhatsApp as a signing communication channel with access links, completion messages and attachment downloads. Requires configured approved message templates, WhatsApp service access and signer phone numbers; document signing remains in the Sign dependency.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "sign",
        "whatsapp",
    ],
    "data": [
        "data/sign_request_whatsapp_templates.xml",
        "data/config_parameter_whatsapp_template.xml",
        "wizards/wizard_sign_request_send_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "auto_install": True,
}
