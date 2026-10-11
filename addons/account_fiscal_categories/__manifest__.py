{
    "name": "Fiscal Category Report",
    "version": "1.0",
    "category": "Accounting/Accounting",
    "summary": "Group account balances by fiscal category and deduction rate",
    "description": "Adds account fiscal categories and dated deduction rates, with a report that groups balances and deductible amounts by category, account and rate.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "account",
    ],
    "data": [
        "data/account_fiscal_report.xml",
        "security/ir.access.csv",
        "views/account_account_views.xml",
        "views/account_fiscal_category_views.xml",
        "views/account_fiscal_report_views.xml",
        "data/account_return_check_template.xml",
        "views/account_fiscal_categories_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "account_fiscal_categories/static/src/components/**/*",
        ],
    },
    "auto_install": True,
}
