{
    "name": "SEPA Direct Debit Checkout",
    "version": "2.0",
    "category": "Accounting/Accounting",
    "sequence": 350,
    "summary": "Create SEPA mandates and payment records from EUR checkout transactions",
    "description": "Adds an IBAN checkout form, mandate-linked payment tokens and matching of initial pending transactions to bank statement lines. Requires a company creditor identifier and an IBAN payment journal. Reused active mandates can confirm transactions before bank collection; payment records must still be submitted to the bank through the accounting workflow. This addon does not contact a bank API.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "account_sepa_direct_debit",
        "account_payment_provider",
        "payment_custom",
    ],
    "data": [
        "reports/empty_mandate_report.xml",
        "views/payment_provider_views.xml",
        "views/payment_sepa_direct_debit_templates.xml",
        "views/sdd_mandate_views.xml",
        "data/ir_cron.xml",
        "data/mail_template_data.xml",
        "data/payment_provider_data.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "payment_sepa_direct_debit/static/src/interactions/payment_form.js",
        ],
    },
    "post_init_hook": "post_init_hook",
    "uninstall_hook": "uninstall_hook",
}
