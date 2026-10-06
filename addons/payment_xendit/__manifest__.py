{
    "name": "Xendit Payments",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Accounting/Payment Providers",
    "sequence": 350,
    "summary": "Accept payments through the Xendit integration",
    "description": "Adds direct card payments and redirect checkout for other supported methods and provider-specific transaction-status handling. Implements saved card payment tokens. Requires a configured Xendit merchant account and credentials; available currencies and payment methods depend on the account and integration configuration. Manual capture and refunds are not implemented.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "payment",
    ],
    "data": [
        "views/payment_provider_views.xml",
        "views/payment_xendit_templates.xml",
        "data/payment_provider_data.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "payment_xendit/static/src/**/*",
        ],
    },
    "post_init_hook": "post_init_hook",
    "uninstall_hook": "uninstall_hook",
}
