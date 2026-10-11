{
    "name": "Inventory Operations Spreadsheet Dashboards",
    "category": "Productivity/Dashboard",
    "summary": "Add Operation analysis, Warehouse Daily Operations spreadsheet dashboards",
    "description": "Install preconfigured spreadsheet dashboards for Operation analysis, Warehouse Daily Operations. The supplied spreadsheet layouts define their business data sources and calculations.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "spreadsheet_dashboard",
        "stock_enterprise",
    ],
    "data": [
        "data/dashboards.xml",
    ],
    "auto_install": [
        "stock_enterprise",
    ],
}
