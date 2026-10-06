{
    "name": "POS Adyen Terminal Payments",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Sales/Point of Sale",
    "sequence": 6,
    "summary": "Process POS payments with Adyen terminals",
    "description": "Adds a Adyen terminal payment method and the POS request and response handling for that integration. Requires a supported terminal and configured provider credentials or payment-provider account.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "point_of_sale",
        "integration",
    ],
    "data": [
        "views/res_config_settings_views.xml",
        "views/pos_payment_method_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_adyen/static/src/**/*",
        ],
        "web.assets_tests": [
            "pos_adyen/static/tests/tours/**/*",
        ],
        "web.assets_unit_tests": [
            "pos_adyen/static/tests/unit/data/**/*",
        ],
    },
}
