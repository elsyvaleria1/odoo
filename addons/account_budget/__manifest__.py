{
    "name": "Analytic Budgets",
    "version": "1.3",
    "oldest_upgradable_version": "1.3",
    "category": "Accounting/Accounting",
    "summary": "Compare analytic budgets with recorded costs and revenues",
    "description": "Define budget periods, lines and revisions and calculate their achieved amounts. Provides budget confirmation, completion and analysis views.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "accountant",
    ],
    "data": [
        "security/account_budget_security.xml",
        "security/ir.access.csv",
        "wizards/wizard_budget_analytic_create_views.xml",
        "views/budget_analytic_views.xml",
        "views/budget_line_view.xml",
        "views/account_analytic_account_views.xml",
        "views/account_move_views.xml",
        "reports/budget_report_view.xml",
        "views/account_budget_menus.xml",
    ],
    "demo": [
        "demo/account_budget_demo.xml",
    ],
    "post_init_hook": "post_init_hook",
}
