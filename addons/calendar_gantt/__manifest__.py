{
    "name": "Appointment Booking Timeline",
    "version": "1.0",
    "category": "Productivity/Calendar",
    "summary": "Display resource and staff bookings on a timeline",
    "description": "Adds Gantt views for calendar bookings, with resource availability and appointment actions adapted to the timeline.",
    "author": "AgroMarin",
    "license": "Other OSI approved licence",
    "depends": [
        "calendar",
        "web_gantt",
    ],
    "data": [
        "views/calendar_event_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "calendar_gantt/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "calendar_gantt/static/tests/**/*",
        ],
    },
    "auto_install": True,
}
