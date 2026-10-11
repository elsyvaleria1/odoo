{
    "name": "Self-Order QFPay Payments",
    "category": "Sales/Point of Sale",
    "summary": "Process kiosk payments through QFPay",
    "description": "Connects the self-order payment flow to the QFPay POS integration and its payment-status handling. Requires that integration and a configured supported terminal.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "pos_qfpay",
        "pos_self_order",
    ],
    "assets": {
        "pos_self_order.assets": [
            "pos_qfpay/static/src/app/qfpay.js",
            "pos_self_order_qfpay/static/src/**/*",
        ],
        "pos_self_order.assets_tests": [
            "pos_qfpay/static/src/app/qfpay.js",
            "pos_qfpay/static/tests/tours/utils/common.js",
            "pos_self_order_qfpay/static/tests/tours/**/*",
        ],
    },
    "auto_install": True,
}
