{
    "name": "eLearning Spreadsheet Dashboards",
    "version": "1.0",
    "category": "Productivity/Dashboard",
    "summary": "Add eLearning spreadsheet dashboards",
    "description": "Install preconfigured spreadsheet dashboards for eLearning. The supplied spreadsheet layouts define their business data sources and calculations.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "spreadsheet_dashboard",
        "website_sale_slides",
    ],
    "data": [
        "data/dashboards.xml",
    ],
    "auto_install": [
        "website_sale_slides",
    ],
}
