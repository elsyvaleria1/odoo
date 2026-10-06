{
    "name": "Self-Order Pine Labs Payments",
    "version": "1.0",
    "category": "Sales/Point of Sale",
    "summary": "Process kiosk payments through Pine Labs",
    "description": "Connects the self-order payment flow to the Pine Labs POS integration and its payment-status handling. Requires that integration and a configured supported terminal.",
    "author": "Odoo IN Pvt Ltd",
    "license": "LGPL-3",
    "depends": [
        "pos_pine_labs",
        "pos_self_order",
    ],
    "assets": {
        "pos_self_order.assets": [
            "pos_self_order_pine_labs/static/src/**/*",
        ],
    },
    "auto_install": True,
}
