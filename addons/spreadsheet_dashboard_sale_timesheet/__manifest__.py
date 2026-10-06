{
    "name": "Timesheets Spreadsheet Dashboards",
    "version": "1.0",
    "category": "Productivity/Dashboard",
    "summary": "Add Timesheets spreadsheet dashboards",
    "description": "Install preconfigured spreadsheet dashboards for Timesheets. The supplied spreadsheet layouts define their business data sources and calculations.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "spreadsheet_dashboard",
        "sale_timesheet",
    ],
    "data": [
        "data/dashboards.xml",
    ],
    "auto_install": [
        "sale_timesheet",
    ],
}
