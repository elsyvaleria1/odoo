{
    "name": "Attendance Timeline",
    "version": "1.0",
    "category": "Human Resources/Attendances",
    "summary": "Review employee attendances and overtime on a timeline",
    "description": "Adds attendance Gantt views with working-hour availability, overtime progress and links to attendance details.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "hr_attendance",
        "hr_gantt",
    ],
    "data": [
        "views/hr_attendance_gantt.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "hr_attendance_gantt/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "hr_attendance_gantt/static/tests/**/*",
        ],
    },
    "auto_install": True,
}
