{
    "name": "POS SMS Receipts",
    "category": "Sales/Point of Sale",
    "summary": "Send POS order messages by SMS",
    "description": "Add an SMS sending action to POS orders and supply its message template. Requires the configured SMS service and recipient phone information.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "point_of_sale",
        "sms",
    ],
    "data": [
        "data/sms_data.xml",
        "views/res_config_settings_views.xml",
        "data/point_of_sale_data.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_sms/static/src/**/*",
        ],
        "web.assets_tests": [
            "pos_sms/static/tests/tours/**/*",
        ],
    },
}
