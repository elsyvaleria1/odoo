{
    "name": "PayPal Payments",
    "version": "2.1",
    "oldest_upgradable_version": "2.1",
    "category": "Accounting/Payment Providers",
    "sequence": 350,
    "summary": "Accept payments through the PayPal integration",
    "description": "Adds direct checkout and provider-specific transaction-status handling. Requires a configured PayPal merchant account and credentials; available currencies and payment methods depend on the account and integration configuration. Tokenization, manual capture and refunds are not implemented.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "payment",
    ],
    "data": [
        "views/payment_form_templates.xml",
        "views/payment_provider_views.xml",
        "views/payment_transaction_views.xml",
        "data/payment_provider_data.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "payment_paypal/static/src/**/*",
        ],
    },
    "post_init_hook": "post_init_hook",
    "uninstall_hook": "uninstall_hook",
}
