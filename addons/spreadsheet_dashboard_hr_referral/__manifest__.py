{
    "name": "Recruitment Spreadsheet Dashboards",
    "version": "1.0",
    "category": "Productivity/Dashboard",
    "summary": "Add Recruitment spreadsheet dashboards",
    "description": "Install preconfigured spreadsheet dashboards for Recruitment. The supplied spreadsheet layouts define their business data sources and calculations.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "spreadsheet_dashboard",
        "hr_referral",
        "hr_contract_salary",
    ],
    "data": [
        "data/dashboards.xml",
    ],
    "auto_install": [
        "hr_referral",
        "hr_contract_salary",
    ],
}
