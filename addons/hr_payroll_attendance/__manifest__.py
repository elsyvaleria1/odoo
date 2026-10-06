{
    "name": "Payroll Attendance Links",
    "category": "Human Resources/Employees",
    "sequence": 95,
    "summary": "Review attendance records associated with payslips",
    "description": "Adds attendance counts and navigation to payslips and adapts overtime worked-day handling to attendance rules.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "hr_work_entry_attendance",
        "hr_payroll",
    ],
    "data": [
        "views/hr_payroll_attendance_views.xml",
        "views/hr_payslip_views.xml",
    ],
    "demo": [
        "demo/hr_payroll_attendance_demo.xml",
    ],
    "auto_install": True,
}
