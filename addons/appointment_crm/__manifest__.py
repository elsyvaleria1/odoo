{
    "name": "Appointment Lead Generation",
    "version": "1.0",
    "category": "Services/Appointment",
    "sequence": 2150,
    "summary": "Create or link CRM leads for appointment types with lead generation enabled",
    "description": "Adds lead-generation settings and links appointment events to opportunities. New leads are created for enabled appointment types with an external attendee and no existing opportunity; eligible existing leads can be reused.",
    "author": "Odoo S.A.",
    "website": "https://www.odoo.com/app/appointments",
    "license": "OEEL-1",
    "depends": [
        "calendar",
        "crm",
    ],
    "data": [
        "views/appointment_type_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "appointment_crm/static/src/views/**/*",
        ],
        "web.assets_tests": [
            "appointment_crm/static/tests/tours/**/*",
        ],
    },
    "auto_install": True,
}
