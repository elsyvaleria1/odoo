{
    "name": "POS - Restaurant Spreadsheet Dashboards",
    "version": "1.0",
    "category": "Productivity/Dashboard",
    "summary": "Add POS - Restaurant spreadsheet dashboards",
    "description": "Install preconfigured spreadsheet dashboards for POS - Restaurant. The supplied spreadsheet layouts define their business data sources and calculations.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "spreadsheet_dashboard",
        "pos_hr",
        "pos_restaurant",
    ],
    "data": [
        "data/dashboards.xml",
    ],
    "auto_install": [
        "pos_hr",
        "pos_restaurant",
    ],
}
