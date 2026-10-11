{
    "name": "Manufacturing Cost Analysis",
    "version": "1.0",
    "category": "Supply Chain/Manufacturing",
    "summary": "Compare manufacturing costs with expected production costs",
    "description": "Add a manufacturing analysis report with expected component, operation and employee costs alongside production costs. Extends manufacturing accounting with reporting views.",
    "author": "Odoo S.A.",
    "website": "https://www.odoo.com/app/manufacturing",
    "license": "Other OSI approved licence",
    "depends": [
        "mrp_account",
    ],
    "data": [
        "security/ir.access.csv",
        "views/mrp_account_view.xml",
        "reports/mrp_report_views.xml",
        "views/mrp_account_enterprise_menus.xml",
    ],
    "demo": [
        "demo/mrp_account_demo.xml",
    ],
    "assets": {
        "web.report_assets_common": [
            "mrp_account_enterprise/static/src/scss/cost_structure_report.scss",
        ],
    },
    "auto_install": True,
}
