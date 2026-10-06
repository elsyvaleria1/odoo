{
    "name": "Calendar Work Locations",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Human Resources/Remote Work",
    "summary": "View and change employee work locations from the calendar",
    "description": "Expose work-location lookup and update actions in calendar scheduling. The update wizard records the selected location for the employee.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "hr_homeworking",
        "calendar",
    ],
    "data": [
        "security/ir.access.csv",
        "wizards/wizard_hr_employee_update_work_location_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "hr_homeworking_calendar/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "hr_homeworking_calendar/static/tests/**/*",
        ],
    },
    "auto_install": True,
}
