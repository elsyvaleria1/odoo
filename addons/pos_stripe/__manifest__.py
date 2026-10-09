{
    "name": "POS Stripe Terminal Payments",
    "version": "1.0",
    "category": "Sales/Point of Sale",
    "sequence": 6,
    "summary": "Process POS payments with Stripe terminals",
    "description": "Adds a Stripe terminal payment method and the POS request and response handling for that integration. Requires a supported terminal and configured provider credentials or payment-provider account.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "point_of_sale",
        "payment_stripe",
    ],
    "data": [
        "views/pos_payment_method_views.xml",
        "views/assets_stripe.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_stripe/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "pos_stripe/static/tests/unit/**/*",
        ],
    },
}
