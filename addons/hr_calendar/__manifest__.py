{
    "name": "Employee Calendar Availability",
    "version": "1.0",
    "category": "Human Resources/Employees",
    "summary": "Show employee working hours and availability in calendar scheduling",
    "description": "Resolve employee schedules for event attendees and calculate unavailable intervals. Adds working-hour information to calendar and partner views.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "hr",
        "calendar",
    ],
    "data": [
        "views/calendar_views_calendarApp.xml",
        "views/res_partner_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "hr_calendar/static/src/**/*",
        ],
    },
    "auto_install": True,
}
