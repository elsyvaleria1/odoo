{
    "name": "Spreadsheet Edition Tests",
    "version": "1.0",
    "category": "Hidden",
    "summary": "Test Spreadsheet Edition behaviour, including spreadsheet history basic rights, spreadsheet controllers, spreadsheet",
    "description": "Run regression tests for Spreadsheet Edition. Loaded test suites include ``SpreadsheetMixinHistoryTest``, ``SpreadsheetMixinControllerTest``, ``SpreadsheetMixinTest``, ``SpreadsheetRevisionTest``.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "spreadsheet_edition",
        "test_spreadsheet",
    ],
    "assets": {
        "spreadsheet.o_spreadsheet": [
            "test_spreadsheet_edition/static/src/**/*.js",
            "test_spreadsheet_edition/static/src/**/*.xml",
        ],
        "web.assets_unit_tests": [
            "test_spreadsheet_edition/static/tests/**/*",
        ],
    },
}
