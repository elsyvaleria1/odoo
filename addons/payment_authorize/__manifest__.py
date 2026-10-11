{
    "name": "Authorize.Net Payments",
    "version": "2.1",
    "oldest_upgradable_version": "2.1",
    "category": "Accounting/Payment Providers",
    "sequence": 350,
    "summary": "Accept payments through the Authorize.Net integration",
    "description": "Adds direct checkout and provider-specific transaction-status handling. Implements saved payment tokens, full capture, cancellation and full refunds. Requires a configured Authorize.Net merchant account and credentials; available currencies and payment methods depend on the account and integration configuration. Partial capture and partial refunds are not implemented.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "payment",
    ],
    "data": [
        "views/payment_authorize_templates.xml",
        "views/payment_provider_views.xml",
        "views/payment_token_views.xml",
        "data/payment_provider_data.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "payment_authorize/static/src/interactions/payment_form.js",
            "payment_authorize/static/src/scss/payment_authorize.scss",
        ],
    },
    "post_init_hook": "post_init_hook",
    "uninstall_hook": "uninstall_hook",
}
