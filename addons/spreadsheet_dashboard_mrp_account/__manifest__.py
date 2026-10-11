{
    "name": "Manufacturing Spreadsheet Dashboards",
    "version": "1.0",
    "category": "Productivity/Dashboard",
    "summary": "Add Manufacturing spreadsheet dashboards",
    "description": "Install preconfigured spreadsheet dashboards for Manufacturing. The supplied spreadsheet layouts define their business data sources and calculations.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "spreadsheet_dashboard",
        "mrp_account_enterprise",
    ],
    "data": [
        "data/dashboards.xml",
    ],
    "auto_install": [
        "mrp_account_enterprise",
    ],
}
