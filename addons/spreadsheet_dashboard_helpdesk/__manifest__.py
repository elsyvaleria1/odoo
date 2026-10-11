{
    "name": "Helpdesk Spreadsheet Dashboards",
    "version": "1.0",
    "category": "Productivity/Dashboard",
    "summary": "Add Helpdesk spreadsheet dashboards",
    "description": "Install preconfigured spreadsheet dashboards for Helpdesk. The supplied spreadsheet layouts define their business data sources and calculations.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "spreadsheet_dashboard",
        "helpdesk",
    ],
    "data": [
        "data/dashboards.xml",
    ],
    "auto_install": [
        "helpdesk",
    ],
}
