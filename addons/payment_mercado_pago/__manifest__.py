{
    "name": "Mercado Pago Payments",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Accounting/Payment Providers",
    "sequence": 350,
    "summary": "Accept payments through the Mercado Pago integration",
    "description": "Adds redirect checkout and provider-specific transaction-status handling. Implements saved payment tokens and OAuth account authorization. Requires a configured Mercado Pago merchant account and credentials; available currencies and payment methods depend on the account and integration configuration. Manual capture and refunds are not implemented.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "payment",
    ],
    "data": [
        "views/payment_form_templates.xml",
        "views/payment_mercado_pago_templates.xml",
        "views/payment_provider_views.xml",
        "data/payment_provider_data.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "payment_mercado_pago/static/src/**/*",
        ],
    },
    "post_init_hook": "post_init_hook",
    "uninstall_hook": "uninstall_hook",
}
