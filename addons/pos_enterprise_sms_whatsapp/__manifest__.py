{
    "name": "POS Preparation Messages",
    "version": "1.0",
    "category": "Sales/Point of Sale",
    "summary": "Notify customers when orders are received or ready",
    "description": "Adds SMS and WhatsApp templates to preparation displays and sends configured notifications on preparation events. Requires the corresponding messaging account and templates.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "pos_enterprise",
        "whatsapp",
        "pos_sms",
        "pos_restaurant",
        "pos_self_order",
    ],
    "data": [
        "data/sms_template.xml",
        "data/whatsapp_template.xml",
        "views/pos_prep_display_view.xml",
    ],
    "assets": {
        "pos_self_order.assets_tests": [
            "pos_enterprise_sms_whatsapp/static/src/tests/tours/pos_self_order_tour.js",
        ],
    },
}
