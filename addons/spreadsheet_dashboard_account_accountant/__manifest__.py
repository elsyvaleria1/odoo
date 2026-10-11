{
    "name": "Accounting Spreadsheet Dashboards",
    "version": "1.0",
    "category": "Productivity/Dashboard",
    "summary": "Add Accounting, Benchmark spreadsheet dashboards",
    "description": "Install preconfigured spreadsheet dashboards for Accounting, Benchmark. The supplied spreadsheet layouts define their business data sources and calculations.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "spreadsheet_dashboard",
        "accountant",
    ],
    "data": [
        "data/dashboards.xml",
    ],
    "auto_install": [
        "accountant",
    ],
}
