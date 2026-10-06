{
    "name": "WhatsApp-Sale",
    "category": "Productivity/WhatsApp",
    "summary": "Provide WhatsApp message templates for sales orders",
    "description": "Load message templates and expose selected sales orders fields for WhatsApp rendering. Sending uses the configured WhatsApp business account and template approval flow.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "sale",
        "whatsapp",
    ],
    "data": [
        "data/whatsapp_template_data.xml",
    ],
    "auto_install": True,
}
