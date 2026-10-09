{
    "name": "POS Viva.com Terminal Payments",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Sales/Point of Sale",
    "sequence": 7,
    "summary": "Process POS payments with Viva.com terminals",
    "description": "Adds a Viva.com terminal payment method and the POS request and response handling for that integration. Requires a supported terminal and configured provider credentials or payment-provider account.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "point_of_sale",
        "integration",
    ],
    "data": [
        "views/pos_payment_method_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_viva_com/static/src/**/*",
        ],
        "web.assets_tests": [
            "pos_viva_com/static/tests/tours/**/*",
        ],
        "web.assets_unit_tests": [
            "pos_viva_com/static/tests/unit/**/*",
        ],
    },
}
