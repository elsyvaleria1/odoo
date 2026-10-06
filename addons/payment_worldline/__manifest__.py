{
    "name": "Worldline Payments",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Accounting/Payment Providers",
    "sequence": 350,
    "summary": "Accept payments through the Worldline integration",
    "description": "Adds redirect checkout and provider-specific transaction-status handling. Implements saving supported payment tokens during payment. Requires a configured Worldline merchant account and credentials; available currencies and payment methods depend on the account and integration configuration. Token-only validation, manual capture and refunds are not implemented.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "payment",
    ],
    "data": [
        "views/payment_provider_views.xml",
        "views/payment_worldline_templates.xml",
        "data/payment_provider_data.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "payment_worldline/static/src/interactions/payment_form.js",
        ],
    },
    "post_init_hook": "post_init_hook",
    "uninstall_hook": "uninstall_hook",
}
