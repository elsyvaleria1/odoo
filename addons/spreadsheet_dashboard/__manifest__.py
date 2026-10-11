{
    "name": "Spreadsheet Dashboards",
    "version": "1.2",
    "oldest_upgradable_version": "1.2",
    "category": "Productivity/Dashboard",
    "summary": "Publish and share grouped spreadsheet dashboards",
    "description": "Defines dashboard groups, company and user-group access, favorites and published spreadsheet content. Provides shared dashboard links and export routes.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "spreadsheet",
    ],
    "data": [
        "security/security.xml",
        "security/ir.access.csv",
        "views/spreadsheet_dashboard_views.xml",
        "views/menu_views.xml",
        "data/dashboard.xml",
    ],
    "assets": {
        "spreadsheet.o_spreadsheet": [
            "spreadsheet_dashboard/static/src/bundle/**/*.js",
            "spreadsheet_dashboard/static/src/bundle/**/*.xml",
        ],
        "spreadsheet.assets_print": [
            "spreadsheet_dashboard/static/src/print_assets/**/*",
        ],
        "web.assets_backend": [
            "spreadsheet_dashboard/static/src/assets/**/*.js",
            "spreadsheet_dashboard/static/src/**/*.scss",
        ],
        "web.assets_unit_tests": [
            "spreadsheet_dashboard/static/tests/**/*",
        ],
    },
}
