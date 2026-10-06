{
    "name": "Sales Spreadsheet Dashboards",
    "version": "1.0",
    "category": "Productivity/Dashboard",
    "summary": "Add Sales, Product spreadsheet dashboards",
    "description": "Install preconfigured spreadsheet dashboards for Sales, Product. The supplied spreadsheet layouts define their business data sources and calculations.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "spreadsheet_dashboard",
        "sale",
        "sale_team",
    ],
    "data": [
        "data/dashboards.xml",
    ],
    "auto_install": [
        "sale",
    ],
}
