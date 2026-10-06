{
    "name": "Appointments with Outlook Calendar",
    "version": "1.0",
    "category": "Productivity",
    "summary": "Configure Microsoft calendar connections for appointment scheduling",
    "description": "Expose connected and available Microsoft calendars on appointment types. Uses the Microsoft Calendar dependency for synchronization.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "microsoft_calendar",
        "calendar",
    ],
    "data": [
        "views/appointment_type_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "appointment_microsoft_calendar/static/src/**/*",
        ],
    },
    "auto_install": True,
}
