{
    "name": "Survey Result Spreadsheets",
    "version": "1.0",
    "category": "Productivity/Documents",
    "summary": "Open survey responses in a linked spreadsheet",
    "description": "Builds spreadsheet data from survey answers and comments and links the resulting document to the survey analysis view.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "document_spreadsheet",
        "survey",
    ],
    "data": [
        "views/survey_templates_statistics.xml",
        "views/survey_survey_views.xml",
    ],
    "assets": {
        "spreadsheet.o_spreadsheet": [
            "document_spreadsheet_survey/static/src/spreadsheet/*.js",
        ],
        "web.assets_unit_tests": [
            "document_spreadsheet_survey/static/tests/**/*",
        ],
    },
    "auto_install": True,
}
