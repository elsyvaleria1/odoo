{
    "name": "POS SIX IoT Payments",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Sales/Point of Sale",
    "summary": "Process POS payments through SIX terminals connected to IoT",
    "description": "Adds a SIX terminal choice and POS payment interface for the IoT integration. Requires a supported terminal connected to a configured IoT installation.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "iot_six",
        "pos_iot",
    ],
    "data": [
        "wizards/wizard_pos_payment_method_update_six_terminal_views.xml",
        "views/pos_payment_method_views.xml",
        "views/iot_box_views.xml",
        "security/ir.access.csv",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_iot_six/static/src/js/balance_button.js",
            "pos_iot_six/static/src/js/models.js",
            "pos_iot_six/static/src/js/payment_six.js",
            "pos_iot_six/static/src/xml/balance_button.xml",
        ],
        "web.assets_backend": [
            "pos_iot_six/static/src/js/six_terminal_id_field.*",
            "pos_iot_six/static/src/css/six_terminal_id_field.css",
        ],
        "web.assets_unit_tests": [
            "pos_iot_six/static/tests/unit/**/*",
        ],
    },
}
