{
    "name": "Leads Spreadsheet Dashboards",
    "version": "1.0",
    "category": "Productivity/Dashboard",
    "summary": "Add Leads, Pipeline spreadsheet dashboards",
    "description": "Install preconfigured spreadsheet dashboards for Leads, Pipeline. The supplied spreadsheet layouts define their business data sources and calculations.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "spreadsheet_dashboard",
        "crm_enterprise",
    ],
    "data": [
        "data/dashboards.xml",
    ],
    "auto_install": [
        "crm_enterprise",
    ],
}
