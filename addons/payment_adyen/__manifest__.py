{
    "name": "Adyen Payments",
    "version": "2.1",
    "oldest_upgradable_version": "2.1",
    "category": "Accounting/Payment Providers",
    "sequence": 350,
    "summary": "Accept payments through the Adyen integration",
    "description": "Adds embedded payment components and provider-specific transaction-status handling. Implements saved payment tokens, full or partial capture, cancellation and full or partial refunds. Requires a configured Adyen merchant account and credentials; available currencies and payment methods depend on the account and integration configuration. Express checkout is not implemented.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "payment",
    ],
    "data": [
        "views/payment_adyen_templates.xml",
        "views/payment_form_templates.xml",
        "views/payment_provider_views.xml",
        "data/payment_provider_data.xml",
        "wizards/wizard_payment_transaction_capture_views.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "payment_adyen/static/src/interactions/payment_form.js",
        ],
    },
    "post_init_hook": "post_init_hook",
    "uninstall_hook": "uninstall_hook",
}
