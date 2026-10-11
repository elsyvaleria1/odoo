{
    "name": "Work Entry Timeline",
    "category": "Human Resources/Employees",
    "sequence": 39,
    "summary": "Review work entries and conflicts on a timeline",
    "description": "Adds employee-grouped Gantt views with availability and progress calculations for work entries.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "hr_work_entry",
        "hr_gantt",
    ],
    "data": [
        "views/hr_payroll_menu.xml",
        "views/hr_work_entry_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "hr_work_entry_enterprise/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "hr_work_entry_enterprise/static/tests/**/*",
        ],
    },
    "auto_install": True,
}
