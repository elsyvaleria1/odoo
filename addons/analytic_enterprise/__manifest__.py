{
    "name": "Analytic Grid Views",
    "version": "0.1",
    "category": "Accounting/Accounting",
    "summary": "Add grid views for analytic accounting",
    "description": "Extend analytic account views with grid presentation. Supplies the year-range computation used by the analytic grid.",
    "author": "Odoo S.A.",
    "website": "https://www.odoo.com/app/accounting",
    "license": "OEEL-1",
    "depends": [
        "web_grid",
        "analytic",
        "account",
    ],
    "data": [
        "views/account_analytic_view.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "analytic_enterprise/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "analytic_enterprise/static/tests/**/*.test.js",
        ],
    },
    "auto_install": True,
}
