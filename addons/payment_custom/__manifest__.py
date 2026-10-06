{
    "name": "Manual Payment Instructions",
    "version": "2.0",
    "category": "Accounting/Payment Providers",
    "sequence": 350,
    "summary": "Display payment instructions and retain transactions for manual confirmation",
    "description": "Adds configurable offline payment instructions, including wire-transfer details. Checkout records a pending transaction; this addon does not contact a bank or automatically establish that funds were received.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "payment",
    ],
    "data": [
        "views/payment_custom_templates.xml",
        "views/payment_provider_views.xml",
        "data/payment_method_data.xml",
        "data/payment_provider_data.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "payment_custom/static/src/interactions/post_processing.js",
        ],
    },
    "post_init_hook": "post_init_hook",
    "uninstall_hook": "uninstall_hook",
}
