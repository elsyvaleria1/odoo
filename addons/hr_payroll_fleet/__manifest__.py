{
    "name": "Payroll Vehicle Data Warnings",
    "version": "1.4",
    "oldest_upgradable_version": "1.3",
    "category": "Human Resources/Payroll",
    "summary": "Warn about vehicle information needed for payroll",
    "description": "Supplies payroll dashboard warning definitions for employee vehicle data. Payroll calculations remain in the payroll and country-specific modules.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "hr_payroll",
        "hr_fleet",
    ],
    "data": [
        "data/hr_payroll_dashboard_warning_data.xml",
    ],
    "auto_install": True,
}
