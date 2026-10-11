{
    "name": "Paid Self-Orders on Preparation Displays",
    "version": "1.0",
    "category": "Sales/Point of Sale",
    "summary": "Update preparation displays after self-order online payment",
    "description": "Extends successful POS online-payment processing to pass paid self-orders into preparation-display handling.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "pos_online_payment_self_order",
        "pos_enterprise",
    ],
    "assets": {
        "pos_self_order.assets_tests": [
            "pos_online_payment_self_order_preparation_display/static/tests/**/*",
        ],
    },
    "auto_install": True,
}
