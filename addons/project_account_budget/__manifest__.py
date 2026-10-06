{
    "name": "Project Analytic Budgets",
    "version": "1.0",
    "category": "Services/Project",
    "summary": "Review analytic budgets and progress from projects",
    "description": "Adds budget totals, progress and line navigation to the project panel and includes budget information in project updates.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "account_budget",
        "project",
    ],
    "data": [
        "views/project_project_views.xml",
        "views/budget_analytic_views.xml",
        "views/project_update_templates.xml",
    ],
    "demo": [
        "demo/budget_analytic_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "project_account_budget/static/src/components/**/*",
        ],
    },
    "auto_install": True,
}
