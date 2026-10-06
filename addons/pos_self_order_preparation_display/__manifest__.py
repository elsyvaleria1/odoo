{
    "name": "Self-Order Preparation Displays",
    "version": "1.0.0",
    "category": "Sales/Point of Sale",
    "sequence": 7,
    "summary": "Send self-service POS orders to preparation displays",
    "description": "Connect self-order processing and cancellation to preparation-display updates. Includes printer-status messages and order details for the display.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "pos_self_order",
        "pos_enterprise",
    ],
    "assets": {
        "pos_preparation_display.assets": [
            "pos_self_order_preparation_display/static/src/override/pos_preparation_display/**/*",
        ],
        "pos_self_order.assets_tests": [
            "pos_self_order_preparation_display/static/tests/**/*",
        ],
    },
    "auto_install": True,
}
