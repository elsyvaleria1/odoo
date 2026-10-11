{
    "name": "Attendance and Leave Balances",
    "version": "1.0",
    "category": "Human Resources",
    "summary": "Connect attendance overtime with leave allocation and deduction",
    "description": "Adds overtime-linked leave types and allocations, overtime balance checks and attendance-versus-leave reporting. The relevant leave and accrual settings determine how attendance hours affect entitlements; the addon does not convert every extra hour automatically.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "hr_attendance",
        "hr_holidays",
    ],
    "data": [
        "security/ir.access.csv",
        "views/hr_leave_allocation_views.xml",
        "views/hr_leave_type_views.xml",
        "views/hr_leave_views.xml",
        "views/hr_employee_views.xml",
        "views/hr_leave_accrual_level_views.xml",
        "views/hr_leave_attendance_report_views.xml",
        "views/hr_attendance_overtime_views.xml",
        "data/hr_holidays_attendance_data.xml",
        "views/hr_holidays_attendance_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "hr_holidays_attendance/static/src/**/*",
        ],
    },
    "auto_install": True,
}
