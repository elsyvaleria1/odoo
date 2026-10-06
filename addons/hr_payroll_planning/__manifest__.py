{
    "name": "Payroll Planning Links",
    "category": "Human Resources/Employees",
    "sequence": 95,
    "summary": "Open planned shifts associated with payslips",
    "description": "Adds planning-slot counts and navigation to payslip forms.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "hr_work_entry_planning",
        "hr_payroll",
    ],
    "data": [
        "views/hr_payslip_views.xml",
    ],
    "auto_install": True,
}
