{
    "name": "Document-to-Dashboard Conversion",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Productivity/Documents",
    "summary": "Create dashboards from Document spreadsheets",
    "description": "Provides a conversion wizard with dashboard group and access-group selection and actions to open the resulting dashboard.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "spreadsheet_dashboard_edition",
        "document_spreadsheet",
    ],
    "data": [
        "security/ir.access.csv",
        "wizards/wizard_document_document_convert_dashboard_views.xml",
        "views/spreadsheet_dashboard_views.xml",
    ],
    "assets": {
        "spreadsheet.o_spreadsheet": [
            (
                "after",
                "spreadsheet/static/src/o_spreadsheet/o_spreadsheet.js",
                "spreadsheet_dashboard_document/static/src/bundle/**/*.js",
            ),
        ],
        "web.assets_backend": [
            "spreadsheet_dashboard_document/static/src/assets/**/*.js",
            "spreadsheet_dashboard_document/static/src/**/*.xml",
        ],
        "web.assets_unit_tests": [
            "spreadsheet_dashboard_document/static/tests/**/*.js",
        ],
        "web.assets_tests": [
            "spreadsheet_dashboard_document/static/tests/tours/*",
        ],
    },
    "auto_install": True,
}
