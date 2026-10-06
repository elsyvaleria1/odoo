{
    "name": "Purchase Budget Commitments",
    "category": "Accounting/Accounting",
    "summary": "Count purchase commitments against analytic budgets",
    "description": """
Count confirmed purchase orders against a budget as committed amounts
---------------------------------------------------------------------
Adds the Committed figure to budget lines and the budget report, so a budget
shows what is already spoken for and not only what has been billed.
""",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "account_budget",
        "purchase",
    ],
    "data": [
        "views/account_analytic_account_views.xml",
        "views/budget_analytic_views.xml",
        "views/budget_line_view.xml",
        "views/purchase_views.xml",
        "reports/budget_report_view.xml",
    ],
    "demo": [
        "demo/account_budget_demo.xml",
    ],
    "auto_install": True,
}
