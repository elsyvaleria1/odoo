{
    "name": "Self-Order Razorpay Payments",
    "version": "1.0",
    "category": "Sales/Point of Sale",
    "summary": "Process kiosk payments through Razorpay",
    "description": "Connects the self-order payment flow to the Razorpay POS integration and its payment-status handling. Requires that integration and a configured supported terminal.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "pos_razorpay",
        "pos_self_order",
    ],
    "assets": {
        "pos_self_order.assets": [
            "pos_self_order_razorpay/static/**/*",
        ],
    },
    "auto_install": True,
}
