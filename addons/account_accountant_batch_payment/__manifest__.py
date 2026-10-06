{
    "name": "Batch Payment Reconciliation",
    "version": "1.0",
    "category": "Accounting",
    "summary": "Reconcile bank statement lines with payment batches",
    "description": "Adds batch-payment selection and removal to bank reconciliation and exposes the journal items belonging to a batch.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "account",
        "account_batch_payment",
    ],
    "assets": {
        "web.assets_backend": [
            "account_accountant_batch_payment/static/src/components/**/*",
        ],
    },
    "auto_install": True,
}
