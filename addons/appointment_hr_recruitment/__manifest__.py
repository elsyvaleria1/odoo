{
    "name": "Recruitment Appointment Links",
    "version": "1.0",
    "category": "Services/Appointment",
    "summary": "Link booked interviews to applicants through invitation codes",
    "description": "Adds applicant invitation codes and booking URL parameters. When a booking includes a matching applicant code, the generated calendar event receives the applicant link; the addon does not infer an applicant for unrelated appointments.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "calendar",
        "hr_recruitment",
    ],
    "data": [
        "data/mail_template_data.xml",
    ],
    "demo": [
        "demo/appointment_hr_recruitment_demo.xml",
    ],
    "assets": {
        "web.assets_tests": [
            "appointment_hr_recruitment/static/tests/tours/**/*",
        ],
    },
    "auto_install": True,
}
