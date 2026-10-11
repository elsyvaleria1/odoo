{
    "name": "Warehouse Metrics Spreadsheet Dashboards",
    "category": "Productivity/Dashboard",
    "summary": "Add Warehouse Metrics spreadsheet dashboards",
    "description": "Install preconfigured spreadsheet dashboards for Warehouse Metrics. The supplied spreadsheet layouts define their business data sources and calculations.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "spreadsheet_dashboard",
        "stock_account",
    ],
    "data": [
        "data/dashboards.xml",
    ],
    "auto_install": [
        "stock_account",
    ],
}
