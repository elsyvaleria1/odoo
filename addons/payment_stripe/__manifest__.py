{
    "name": "Stripe Payments",
    "version": "2.1",
    "oldest_upgradable_version": "2.1",
    "category": "Accounting/Payment Providers",
    "sequence": 350,
    "summary": "Accept payments through the Stripe integration",
    "description": "Adds embedded payment elements and provider-specific transaction-status handling. Implements saved payment tokens, full capture, cancellation, full or partial refunds and express checkout. Requires a configured Stripe merchant account and credentials; available currencies and payment methods depend on the account and integration configuration. Partial capture is not implemented.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "payment",
    ],
    "data": [
        "views/payment_provider_views.xml",
        "views/payment_stripe_templates.xml",
        "views/payment_templates.xml",
        "data/payment_provider_data.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "payment_stripe/static/src/interactions/**/*",
            "payment_stripe/static/src/**/*",
        ],
    },
    "post_init_hook": "post_init_hook",
    "uninstall_hook": "uninstall_hook",
}
