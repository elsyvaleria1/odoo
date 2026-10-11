{
    "name": "Workforce ESG Metrics",
    "version": "1.0",
    "category": "ESG",
    "summary": "Analyze workforce distribution and pay-gap metrics",
    "description": "Adds an employee reporting model and dashboard data based on gender, department, leadership, country and wage records. Results depend on the completeness of employee data.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "esg",
        "hr",
    ],
    "data": [
        "security/ir.access.csv",
        "reports/esg_employee_report_views.xml",
        "views/esg_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "esg_hr/static/src/**/*",
        ],
    },
    "auto_install": True,
}
