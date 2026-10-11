{
    "name": "Simulated Payments",
    "version": "2.0",
    "category": "Accounting/Accounting",
    "sequence": 350,
    "summary": "Simulate payment outcomes for demonstrations and testing",
    "description": "Provides selectable payment outcomes and simulated saved tokens, captures, cancellations, refunds and express checkout. No money is collected and no payment provider is contacted.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "payment",
    ],
    "data": [
        "views/payment_demo_templates.xml",
        "views/payment_provider_views.xml",
        "views/payment_token_views.xml",
        "views/payment_transaction_views.xml",
        "data/payment_method_data.xml",
        "data/payment_provider_data.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "payment_demo/static/src/interactions/**/*",
        ],
    },
    "post_init_hook": "post_init_hook",
    "uninstall_hook": "uninstall_hook",
}
