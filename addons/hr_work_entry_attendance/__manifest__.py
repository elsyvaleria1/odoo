{
    "name": "Attendance Work Entries",
    "category": "Human Resources/Employees",
    "sequence": 95,
    "summary": "Generate employee work entries from attendance records",
    "description": "Adds attendance as a work-entry source, links entries to attendance and overtime records and updates them when the source attendance changes.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "hr_work_entry",
        "hr_attendance",
    ],
    "data": [
        "data/hr_attendance_overtime_rule_data.xml",
        "views/hr_attendance_overtime_views.xml",
        "views/hr_employee_views.xml",
        "views/hr_contract_template_views.xml",
    ],
    "demo": [
        "demo/hr_work_entry_attendance_demo.xml",
    ],
    "auto_install": True,
}
