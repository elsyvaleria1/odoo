{
    "name": "Self-Order Online Payments",
    "version": "1.0",
    "category": "Sales/Point of Sale",
    "summary": "Collect online payments for POS self-service orders",
    "description": "Adds a self-order online payment method and links provider transaction confirmation to the order payment status. Requires a configured online payment provider.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "pos_online_payment",
        "pos_self_order",
    ],
    "data": [
        "views/res_config_settings_views.xml",
    ],
    "assets": {
        "pos_self_order.assets": [
            "pos_online_payment_self_order/static/src/app/**/*",
            "point_of_sale/static/lib/qrcode.js",
        ],
        "point_of_sale._assets_pos": [
            "pos_online_payment_self_order/static/src/overrides/**/*",
        ],
        "web.assets_tests": [
            "pos_online_payment_self_order/static/tests/tours/pos_online_payment_multi_table_order.js",
        ],
        "pos_self_order.assets_tests": [
            "pos_online_payment_self_order/static/tests/tours/pos_self_order_mobile_online_payment_tour.js",
        ],
        "web.assets_unit_tests": [
            "pos_online_payment_self_order/static/tests/unit/**/*",
        ],
    },
    "auto_install": True,
}
