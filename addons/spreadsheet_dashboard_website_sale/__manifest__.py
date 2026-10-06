{
    "name": "eCommerce Spreadsheet Dashboards",
    "version": "1.0",
    "category": "Productivity/Dashboard",
    "summary": "Add eCommerce spreadsheet dashboards",
    "description": "Install preconfigured spreadsheet dashboards for eCommerce. The supplied spreadsheet layouts define their business data sources and calculations.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "spreadsheet_dashboard",
        "website_sale",
    ],
    "data": [
        "data/dashboards.xml",
    ],
    "auto_install": [
        "website_sale",
    ],
}
