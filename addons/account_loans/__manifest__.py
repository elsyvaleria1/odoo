{
    "name": "Loan Accounting",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Accounting/Accounting",
    "sequence": 32,
    "summary": "Build loan repayment schedules and related accounting entries",
    "description": "Manage loan terms, schedule lines and repayment state. Provides actions to generate schedules, post accounting entries and close loans.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "account_depreciation",
        "accountant",
        "account",
        "base_import",
    ],
    "data": [
        "security/ir.access.csv",
        "wizards/wizard_account_loan_close_views.xml",
        "wizards/wizard_account_loan_create_schedule_views.xml",
        "views/account_asset_views.xml",
        "views/account_asset_group_views.xml",
        "views/account_loan_views.xml",
        "views/account_move_views.xml",
        "data/account_return_check_template.xml",
        "views/account_loans_menus.xml",
    ],
    "demo": [
        "demo/account_loans_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "account_loans/static/src/**/*",
        ],
    },
    "auto_install": True,
    "post_init_hook": "_account_loans_post_init",
}
