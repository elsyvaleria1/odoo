{
    "name": "Planning Leave Warnings",
    "version": "1.0",
    "category": "Human Resources/Planning",
    "sequence": 50,
    "summary": "Show employee leave conflicts on shifts and refresh affected planned hours",
    "description": "Adds leave warnings and absence filters for assigned current or future shifts. Schedule-exception changes trigger allocated-hour recomputation for affected shifts; leave requests and approval remain in the Time Off dependency.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "planning",
        "hr_holidays_gantt",
    ],
    "data": [
        "views/planning_slot_views.xml",
        "reports/planning_report_views.xml",
    ],
    "assets": {
        "web.assets_unit_tests": [
            "planning_holidays/static/tests/**/*",
        ],
    },
    "auto_install": True,
}
