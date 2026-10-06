{
    "name": "Website Appointment Lead Enrichment",
    "version": "1.0",
    "category": "Services/Appointment",
    "sequence": 2160,
    "summary": "Add matching website visitor context to appointment-generated leads",
    "description": "Extends appointment lead values with the current visitor link and missing country or language values. It applies only when the visitor has no contact or its contact matches the appointment partner; lead generation itself comes from Appointment CRM.",
    "author": "Odoo S.A.",
    "website": "https://www.odoo.com/app/appointments",
    "license": "OEEL-1",
    "depends": [
        "appointment_crm",
        "website_crm",
    ],
    "assets": {
        "web.assets_tests": [
            "website_appointment_crm/static/tests/tours/**/*",
        ],
    },
    "auto_install": True,
}
