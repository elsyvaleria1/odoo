{
    "name": "Expenses Spreadsheet Dashboards",
    "version": "1.0",
    "category": "Productivity/Dashboard",
    "summary": "Add Expenses spreadsheet dashboards",
    "description": "Install preconfigured spreadsheet dashboards for Expenses. The supplied spreadsheet layouts define their business data sources and calculations.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "spreadsheet_dashboard",
        "sale_expense",
    ],
    "data": [
        "data/dashboards.xml",
    ],
    "auto_install": [
        "sale_expense",
    ],
}
