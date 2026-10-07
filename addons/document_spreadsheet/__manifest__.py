{
    "name": "Document Spreadsheets",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Productivity/Documents",
    "summary": "Create, edit and share spreadsheets stored in Documents",
    "description": "Adds spreadsheet document handling, templates, collaboration messages, CSV/XLSX import and spreadsheet sharing controls. Access follows the document and spreadsheet permissions.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "document",
        "spreadsheet_edition",
        "base_import",
    ],
    "data": [
        "security/ir.access.csv",
        "security/ir_access.xml",
        "views/document_document_views.xml",
        "views/spreadsheet_template_views.xml",
        "views/sharing_templates.xml",
        "views/res_config_settings_views.xml",
        "wizards/wizard_document_document_share_views.xml",
        "wizards/wizard_spreadsheet_template_create_views.xml",
        "views/document_spreadsheet_menus.xml",
    ],
    "demo": [
        "demo/document_document_demo.xml",
    ],
    "assets": {
        "spreadsheet.o_spreadsheet": [
            "document_spreadsheet/static/src/bundle/**/*.js",
            "document_spreadsheet/static/src/bundle/**/*.xml",
        ],
        "web.assets_backend": [
            "document_spreadsheet/static/src/bundle/**/*.scss",
            "document_spreadsheet/static/src/document_view/**/*",
            "document_spreadsheet/static/src/spreadsheet_clone_xlsx_dialog/**/*",
            "document_spreadsheet/static/src/spreadsheet_template/**/*",
            "document_spreadsheet/static/src/helpers.js",
            "document_spreadsheet/static/src/spreadsheet_action_loader.js",
            "document_spreadsheet/static/src/mail/**/*",
            "document_spreadsheet/static/src/views/**/*",
        ],
        "web.assets_tests": [
            "document_spreadsheet/static/tests/tours/*",
        ],
        "web.assets_unit_tests": [
            "document_spreadsheet/static/tests/**/*",
        ],
    },
    "auto_install": [
        "document",
    ],
}
