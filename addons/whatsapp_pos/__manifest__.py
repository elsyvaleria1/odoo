{
    "name": "WhatsApp-POS",
    "category": "Productivity/WhatsApp",
    "summary": "Send POS receipts and invoice messages through WhatsApp",
    "description": "Configure WhatsApp templates for POS receipts and invoices and send them from POS orders. Uses the WhatsApp message composer and configured business account.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "point_of_sale",
        "whatsapp",
    ],
    "data": [
        "data/whatsapp_template_data.xml",
        "views/res_config_settings_views.xml",
        "views/pos_order_views.xml",
    ],
    "demo": [
        "demo/point_of_sale_demo.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "whatsapp_pos/static/src/**/*",
        ],
    },
    "auto_install": True,
}
