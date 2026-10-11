{
    "name": "Paymob Payments",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Accounting/Payment Providers",
    "sequence": 350,
    "summary": "Accept payments through the Paymob integration",
    "description": "Adds redirect checkout and provider-specific transaction-status handling. Requires a configured Paymob merchant account and credentials; available currencies and payment methods depend on the account and integration configuration. Tokenization, manual capture and refunds are not implemented.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "payment",
    ],
    "data": [
        "views/payment_paymob_templates.xml",
        "views/payment_provider_views.xml",
        "data/payment_provider_data.xml",
    ],
    "post_init_hook": "post_init_hook",
    "uninstall_hook": "uninstall_hook",
}
