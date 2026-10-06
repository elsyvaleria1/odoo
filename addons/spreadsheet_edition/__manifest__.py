{
    "name": "Collaborative Spreadsheet Editing",
    "version": "1.0",
    "category": "Productivity/Dashboard",
    "summary": "Edit shared spreadsheets with revisions and cell discussions",
    "description": "Extend spreadsheet records with collaborative messages, revisions and snapshots. Adds cell discussion threads and spreadsheet download routes.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "spreadsheet",
        "mail",
    ],
    "data": [
        "security/ir.access.csv",
        "views/spreadsheet_views.xml",
        "data/mail_template_layouts.xml",
        "views/spreadsheet_edition_menus.xml",
    ],
    "assets": {
        "spreadsheet.o_spreadsheet": [
            "spreadsheet_edition/static/src/bundle/**/*.js",
            "spreadsheet_edition/static/src/bundle/**/filter_editor_side_panel.xml",
            "spreadsheet_edition/static/src/bundle/**/*.xml",
            (
                "remove",
                "spreadsheet_edition/static/src/bundle/pivot/pivot.xml",
            ),
        ],
        "spreadsheet.assets_print": [
            "spreadsheet_edition/static/src/print_assets/**/*",
        ],
        "web.assets_backend": [
            "spreadsheet_edition/static/src/**/*.scss",
            "spreadsheet_edition/static/src/assets/**/*",
            "spreadsheet_edition/static/src/bundle/pivot/pivot.xml",
        ],
        "web.assets_unit_tests": [
            "spreadsheet_edition/static/tests/**/*",
        ],
    },
    "auto_install": True,
}
