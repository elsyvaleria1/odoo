{
    "name": "Events Spreadsheet Dashboards",
    "version": "1.0",
    "category": "Productivity/Dashboard",
    "summary": "Add Events spreadsheet dashboards",
    "description": "Install preconfigured spreadsheet dashboards for Events. The supplied spreadsheet layouts define their business data sources and calculations.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "spreadsheet_dashboard",
        "event_sale",
    ],
    "data": [
        "data/dashboards.xml",
    ],
    "auto_install": [
        "event_sale",
    ],
}
