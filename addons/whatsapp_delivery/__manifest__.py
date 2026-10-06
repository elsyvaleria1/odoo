{
    "name": "WhatsApp-Delivery",
    "category": "Productivity/WhatsApp",
    "summary": "Provide WhatsApp message templates for stock transfers",
    "description": "Load message templates and expose selected stock transfers fields for WhatsApp rendering. Sending uses the configured WhatsApp business account and template approval flow.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "stock_delivery",
        "whatsapp",
    ],
    "data": [
        "data/whatsapp_template_data.xml",
    ],
    "auto_install": True,
}
