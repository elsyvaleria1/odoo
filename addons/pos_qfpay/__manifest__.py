{
    "name": "POS QFPay Terminal Payments",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Sales/Point of Sale",
    "sequence": 6,
    "summary": "Process POS payments with QFPay terminals",
    "description": "Adds a QFPay terminal payment method and the POS request and response handling for that integration. Requires a supported terminal and configured provider credentials or payment-provider account.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "point_of_sale",
        "integration",
    ],
    "data": [
        "views/pos_payment_method_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_qfpay/static/src/**/*",
        ],
        "web.assets_tests": [
            "pos_qfpay/static/src/app/qfpay.js",
            "pos_qfpay/static/tests/tours/**/*",
        ],
    },
}
