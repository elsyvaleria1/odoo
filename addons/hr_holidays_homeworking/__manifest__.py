{
    "name": "Time Off Workplace Presence",
    "category": "Human Resources",
    "summary": "Reflect time off in employee workplace presence indicators",
    "description": "Extends the employee presence calculation and frontend presence display when time off and homeworking are installed together.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "hr_holidays",
        "hr_homeworking",
    ],
    "assets": {
        "web.assets_backend": [
            "hr_holidays_homeworking/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "hr_holidays_homeworking/static/tests/**/*",
        ],
    },
    "auto_install": True,
}
