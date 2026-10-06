{
    "name": "Invoicing Spreadsheet Dashboards",
    "version": "1.0",
    "category": "Productivity/Dashboard",
    "summary": "Add Invoicing spreadsheet dashboards",
    "description": "Install preconfigured spreadsheet dashboards for Invoicing. The supplied spreadsheet layouts define their business data sources and calculations.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "spreadsheet_dashboard",
        "account",
    ],
    "data": [
        "data/dashboards.xml",
    ],
    "auto_install": [
        "account",
    ],
}
