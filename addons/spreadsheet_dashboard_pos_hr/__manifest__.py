{
    "name": "Point of Sale Spreadsheet Dashboards",
    "version": "1.0",
    "category": "Productivity/Dashboard",
    "summary": "Add Point of Sale spreadsheet dashboards",
    "description": "Install preconfigured spreadsheet dashboards for Point of Sale. The supplied spreadsheet layouts define their business data sources and calculations.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "spreadsheet_dashboard",
        "pos_hr",
    ],
    "data": [
        "data/dashboards.xml",
    ],
    "auto_install": [
        "pos_hr",
    ],
}
