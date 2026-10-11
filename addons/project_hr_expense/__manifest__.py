{
    "name": "Project Expenses",
    "version": "1.0",
    "category": "Services/Project",
    "summary": "Include employee expenses in project profitability",
    "description": "Uses project analytic distributions on expenses and adds expense drilldowns and amounts to the project profitability panel.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "project_account",
        "hr_expense",
    ],
    "data": [
        "views/project_project_views.xml",
    ],
    "demo": [
        "demo/project_hr_expense_demo.xml",
    ],
    "auto_install": True,
}
