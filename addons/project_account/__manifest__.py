{
    "name": "Project Accounting Profitability",
    "category": "Accounting/Accounting",
    "summary": "Add vendor bill costs and other analytic amounts to project profitability",
    "description": "Extends profitability for projects with an analytic account using eligible vendor bills and refunds, plus analytic entries without journal-item links. Separates other costs and revenues and provides accounting drill-downs where user access permits; amounts depend on the entries and analytic allocation.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "account",
        "project",
    ],
    "data": [
        "views/account_analytic_line_views.xml",
        "views/project_project_views.xml",
        "views/project_task_views.xml",
        "views/project_sharing_project_task_views.xml",
    ],
    "auto_install": True,
}
