{
    "name": "POS Razorpay Terminals",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Sales/Point of Sale",
    "sequence": 6,
    "summary": "Request, track and refund Razorpay terminal payments for INR companies",
    "description": "Adds payment initiation, status lookup, cancellation and refund requests through the Razorpay POS integration. Requires merchant credentials, a configured terminal and a company whose currency is INR; available payment instruments depend on the provider and terminal.",
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
            "pos_razorpay/static/src/**/*",
        ],
        "web.assets_tests": [
            "pos_razorpay/static/tests/tours/**/*",
        ],
        "web.assets_unit_tests": [
            "pos_razorpay/static/tests/unit/data/**/*",
        ],
    },
}
