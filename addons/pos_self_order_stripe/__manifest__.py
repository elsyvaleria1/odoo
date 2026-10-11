{
    "name": "Self-Order Stripe Payments",
    "category": "Sales/Point of Sale",
    "summary": "Process kiosk payments through Stripe",
    "description": "Connects the self-order payment flow to the Stripe POS integration and its payment-status handling. Requires that integration and a configured supported terminal.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "pos_stripe",
        "pos_self_order",
    ],
    "data": [
        "views/assets_stripe.xml",
    ],
    "assets": {
        "pos_self_order.assets": [
            "pos_self_order_stripe/static/src/**/*",
        ],
        "pos_self_order.assets_tests": [
            "pos_self_order_stripe/static/tests/tours/**/*",
        ],
    },
    "auto_install": True,
}
