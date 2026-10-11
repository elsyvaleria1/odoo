{
    "name": "Analytic Accounting",
    "version": "1.5",
    "oldest_upgradable_version": "1.5",
    "category": "Accounting/Accounting",
    "summary": "Allocate and analyse costs and revenues with analytic plans and accounts",
    "description": "Define analytic plans, accounts, distributions and entries. Analytic records classify business amounts independently of the general-ledger account structure.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "mail",
    ],
    "data": [
        "security/analytic_security.xml",
        "security/ir.access.csv",
        "views/analytic_line_views.xml",
        "views/analytic_account_views.xml",
        "views/analytic_plan_views.xml",
        "views/analytic_distribution_model_views.xml",
        "data/analytic_data.xml",
    ],
    "demo": [
        "demo/analytic_account_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "analytic/static/src/components/**/*",
            "analytic/static/src/services/**/*",
            "analytic/static/src/views/**/*",
        ],
        "web.assets_unit_tests": [
            "analytic/static/tests/**/*",
        ],
    },
}
