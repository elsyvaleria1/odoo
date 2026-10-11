{
    "name": "Spreadsheet Accounting Functions",
    "version": "1.0",
    "category": "Accounting",
    "summary": "Query accounting balances and fiscal periods from spreadsheets",
    "description": "Adds spreadsheet functions and server queries for debit, credit, residual amounts, partner balances and accounting tags, with fiscal-date helpers and journal-item drilldowns.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "spreadsheet",
        "account",
    ],
    "assets": {
        "spreadsheet.o_spreadsheet": [
            (
                "after",
                "spreadsheet/static/src/o_spreadsheet/o_spreadsheet.js",
                "spreadsheet_account/static/src/**/*.js",
            ),
        ],
        "web.assets_unit_tests": [
            "spreadsheet_account/static/tests/**/*",
        ],
    },
    "auto_install": True,
}
