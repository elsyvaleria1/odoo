{
    "name": "Online Bank Batch Payment Initiation",
    "category": "Accounting/Payment",
    "summary": "Initiate and track eligible SEPA credit-transfer batches through a linked bank service",
    "description": "Adds online initiation, signing and status polling for SEPA credit-transfer batches on payment-enabled bank links. Requires online bank connectivity and provider activation; identity verification may be required. This is an outgoing batch-payment integration, not customer invoice checkout.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "account_online_synchronization",
        "account_batch_payment",
        "account_iso20022",
    ],
    "data": [
        "data/actions.xml",
        "data/activation_mail_template.xml",
        "data/success_mail_template.xml",
        "views/account_batch_payment_views.xml",
        "views/account_online_link_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "account_online_payment/static/src/components/**/*",
        ],
    },
    "auto_install": True,
}
