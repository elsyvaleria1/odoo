{
    "name": "Appointments with Google Calendar",
    "version": "1.0",
    "category": "Productivity",
    "summary": "Use Google Calendar connections and video links for appointments",
    "description": "Expose Google connection setup on appointment types. Synchronize the booked event's videoconference information through the Google Calendar integration.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "google_calendar",
        "calendar",
    ],
    "data": [
        "views/appointment_templates_validation.xml",
        "views/appointment_type_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "appointment_google_calendar/static/src/**/*",
        ],
    },
    "auto_install": True,
}
