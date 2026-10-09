{
    "name": "Restaurant Stripe Tips",
    "version": "1.0",
    "category": "Sales/Point of Sale",
    "sequence": 6,
    "summary": "Handle Stripe terminal tips in restaurant payments",
    "description": "Extends the restaurant POS frontend for Stripe tipping. Requires a configured Stripe terminal payment method.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "pos_stripe",
        "pos_restaurant",
        "payment_stripe",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_restaurant_stripe/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "pos_restaurant_stripe/static/tests/unit/**/*",
        ],
    },
    "auto_install": True,
}
