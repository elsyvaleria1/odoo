{
    "name": "Whatsapp Accounting",
    "category": "Productivity/WhatsApp",
    "summary": "Provide WhatsApp message templates for invoices and payments",
    "description": "Load message templates and expose selected invoices and payments fields for WhatsApp rendering. Sending uses the configured WhatsApp business account and template approval flow.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "account",
        "whatsapp",
    ],
    "data": [
        "data/whatsapp_template_data.xml",
    ],
    "auto_install": True,
}
