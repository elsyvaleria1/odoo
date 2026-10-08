{
    "name": "Appointments with Google Calendar",
    "version": "1.1",
    "category": "Productivity",
    "summary": "Google Meet links for appointments booked with Google Calendar synchronization",
    "description": "Offer Google Meet as an appointment type's videoconference: a booked event synchronized with its organizer's Google Calendar gets its Meet link, and staff who do not synchronize are named on the type.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "calendar_google",
        "calendar",
    ],
    "data": [
        "views/appointment_templates_validation.xml",
        "views/appointment_type_views.xml",
    ],
    "auto_install": True,
}
