{
    "name": "WhatsApp Website Order Confirmation",
    "category": "Productivity/WhatsApp",
    "summary": "Send configured WhatsApp confirmations for website sales",
    "description": "Adds a website-specific WhatsApp template setting and sends the selected template when applicable website orders are confirmed.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "website_sale",
        "whatsapp",
    ],
    "data": [
        "views/res_config_settings_views.xml",
    ],
    "demo": [
        "demo/demo.xml",
    ],
    "auto_install": True,
}
