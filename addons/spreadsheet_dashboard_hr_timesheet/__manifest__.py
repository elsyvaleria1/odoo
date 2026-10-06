{
    "name": "Project Spreadsheet Dashboards",
    "version": "1.0",
    "category": "Productivity/Dashboard",
    "summary": "Add Project spreadsheet dashboards",
    "description": "Install preconfigured spreadsheet dashboards for Project. The supplied spreadsheet layouts define their business data sources and calculations.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "spreadsheet_dashboard",
        "hr_timesheet",
    ],
    "data": [
        "data/dashboards.xml",
    ],
    "auto_install": [
        "hr_timesheet",
    ],
}
