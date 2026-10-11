{
    "name": "Personal View Dashboards",
    "version": "1.0",
    "category": "Productivity",
    "sequence": 225,
    "summary": "Save application views and filters in a personal dashboard",
    "description": "Adds dashboard rendering and an action that stores selected views, domains and context in a user-specific customized view. Users can arrange available application views; underlying record permissions still determine the data shown, and source applications provide the reports.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "spreadsheet_dashboard",
    ],
    "data": [
        "security/ir.access.csv",
        "views/board_views.xml",
        "views/board_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "board/static/src/**/*.scss",
            "board/static/src/**/*.js",
            "board/static/src/**/*.xml",
        ],
        "web.assets_unit_tests": [
            "board/static/tests/**/*.test.js",
        ],
    },
}
