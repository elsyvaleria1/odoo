{
    "name": "Email Marketing Spreadsheet Dashboards",
    "version": "1.0",
    "category": "Productivity/Dashboard",
    "summary": "Add Email Marketing spreadsheet dashboards",
    "description": "Install preconfigured spreadsheet dashboards for Email Marketing. The supplied spreadsheet layouts define their business data sources and calculations.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "spreadsheet_dashboard",
        "marketing_automation",
    ],
    "data": [
        "data/dashboards.xml",
    ],
    "auto_install": [
        "marketing_automation",
    ],
}
