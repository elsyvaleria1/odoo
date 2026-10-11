{
    "name": "Spreadsheet Formula Report Values",
    "version": "1.0",
    "category": "Hidden",
    "summary": "Retrieve formula-report values in spreadsheet cells with ODOO.REPORT",
    "description": "Adds a spreadsheet function and batched server lookup for report expressions selected by report reference, line code, expression label and period. Supports company and unposted-entry options and uses the report engine for evaluation; the report and expression must exist and the user must have applicable access.",
    "author": "AgroMarin",
    "license": "Other OSI approved licence",
    "depends": [
        "report_formula",
        "spreadsheet",
    ],
    "assets": {
        "spreadsheet.o_spreadsheet": [
            (
                "after",
                "spreadsheet/static/src/o_spreadsheet/o_spreadsheet.js",
                "spreadsheet_report_formula/static/src/**/*.js",
            ),
        ],
        "web.assets_unit_tests": [
            "spreadsheet_report_formula/static/tests/**/*",
        ],
    },
    "auto_install": True,
}
