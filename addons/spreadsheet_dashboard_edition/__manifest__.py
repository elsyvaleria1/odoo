{
    "name": "Spreadsheet Dashboard Editing",
    "version": "1.0",
    "category": "Productivity/Dashboard",
    "summary": "Edit spreadsheet dashboard content and comments",
    "description": "Adds an editor action, spreadsheet metadata and cell-thread access checks for dashboards.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "spreadsheet_dashboard",
        "spreadsheet_edition",
    ],
    "data": [
        "views/spreadsheet_dashboard_views.xml",
        "security/ir.access.csv",
        "security/ir_access.xml",
    ],
    "assets": {
        "spreadsheet.o_spreadsheet": [
            "spreadsheet_dashboard_edition/static/src/bundle/**/*.js",
        ],
        "web.assets_backend": [
            "spreadsheet_dashboard_edition/static/src/assets/**/*.js",
            "spreadsheet_dashboard_edition/static/src/**/*.scss",
            "spreadsheet_dashboard_edition/static/src/**/*.xml",
        ],
        "spreadsheet.assets_print": [
            "spreadsheet_dashboard_edition/static/src/print_assets/**/*",
        ],
        "web.assets_unit_tests": [
            "spreadsheet_dashboard_edition/static/tests/**/*",
        ],
    },
    "auto_install": True,
}
