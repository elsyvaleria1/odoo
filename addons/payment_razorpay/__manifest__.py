{
    "name": "Razorpay Payments",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Accounting/Payment Providers",
    "sequence": 350,
    "summary": "Accept payments through the Razorpay integration",
    "description": "Adds direct checkout and provider-specific transaction-status handling. Implements saved payment tokens, full capture, cancellation and full or partial refunds. Requires a configured Razorpay merchant account and credentials; available currencies and payment methods depend on the account and integration configuration. Partial capture is not implemented.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "payment",
    ],
    "data": [
        "views/payment_provider_views.xml",
        "views/payment_razorpay_templates.xml",
        "data/payment_provider_data.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "payment_razorpay/static/src/interactions/payment_form.js",
        ],
    },
    "post_init_hook": "post_init_hook",
    "uninstall_hook": "uninstall_hook",
}
