{
    "name": "Batch Payments",
    "version": "1.2",
    "oldest_upgradable_version": "1.2",
    "category": "Accounting/Accounting",
    "summary": "Group payments into batches for bank processing and reconciliation",
    "description": "Create inbound and outbound payment batches for a journal and payment method. File generation is supplied by the applicable payment-format integrations.",
    "author": "Odoo S.A.",
    "website": "https://www.odoo.com/app/accounting",
    "license": "OEEL-1",
    "depends": [
        "account",
    ],
    "data": [
        "security/ir.access.csv",
        "data/account_batch_payment_data.xml",
        "reports/account_batch_payment_reports.xml",
        "reports/account_batch_payment_report_templates.xml",
        "views/account_batch_payment_views.xml",
        "views/account_payment_views.xml",
        "views/account_journal_views.xml",
        "wizards/wizard_account_batch_payment_validate_error_views.xml",
        "wizards/wizard_account_payment_create_batch_partial_views.xml",
        "views/account_batch_payment_menus.xml",
    ],
    "assets": {
        "web.report_assets_common": [
            "account_batch_payment/static/src/scss/**/*",
        ],
    },
}
