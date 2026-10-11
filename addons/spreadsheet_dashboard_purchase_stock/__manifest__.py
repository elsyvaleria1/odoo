{
    "name": "Purchasing Spreadsheet Dashboards",
    "category": "Productivity/Dashboard",
    "summary": "Add Purchase & Vendor analysis spreadsheet dashboards",
    "description": "Install preconfigured spreadsheet dashboards for Purchase & Vendor analysis. The supplied spreadsheet layouts define their business data sources and calculations.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "spreadsheet_dashboard",
        "purchase_stock",
        "stock_enterprise",
    ],
    "data": [
        "data/dashboards.xml",
    ],
    "auto_install": [
        "purchase_stock",
        "stock_enterprise",
    ],
}
