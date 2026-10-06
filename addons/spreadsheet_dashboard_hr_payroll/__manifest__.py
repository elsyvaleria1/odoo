{
    "name": "Payroll Spreadsheet Dashboards",
    "version": "1.0",
    "category": "Productivity/Dashboard",
    "summary": "Add Payroll spreadsheet dashboards",
    "description": "Install preconfigured spreadsheet dashboards for Payroll. The supplied spreadsheet layouts define their business data sources and calculations.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "spreadsheet_dashboard",
        "hr_payroll",
    ],
    "data": [
        "data/dashboards.xml",
    ],
    "auto_install": [
        "hr_payroll",
    ],
}
