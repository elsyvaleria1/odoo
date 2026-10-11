{
    "name": "Appointment Employee Availability",
    "version": "1.0",
    "category": "Services/Appointment",
    "sequence": 2140,
    "summary": "Restrict appointment slots using linked employee working schedules",
    "description": "Adds employee work-interval checks to appointment availability. Applies configured non-flexible employee calendars to eligible staff users; the appointment setting controls whether employee working hours restrict the slots.",
    "author": "Odoo S.A.",
    "website": "https://www.odoo.com/app/appointments",
    "license": "Other OSI approved licence",
    "depends": [
        "calendar",
        "hr",
    ],
    "data": [
        "views/appointment_type_views.xml",
    ],
    "auto_install": True,
}
