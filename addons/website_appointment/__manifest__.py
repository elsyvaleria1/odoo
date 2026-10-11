{
    "name": "Website Appointment Booking",
    "version": "1.1",
    "category": "Services/Appointment",
    "sequence": 215,
    "summary": "Let website visitors book available appointment slots",
    "description": "Publish appointment types and booking pages on websites. Creates calendar events from the selected slots and supports appointment invitation links.",
    "author": "Odoo S.A.",
    "website": "https://www.odoo.com/app/appointments",
    "license": "Other OSI approved licence",
    "depends": [
        "calendar",
        "website_enterprise",
        "website_partner",
        "html_builder",
    ],
    "data": [
        "data/website_data.xml",
        "data/website_snippet_data.xml",
        "views/appointment_type_views.xml",
        "views/appointment_invite_views.xml",
        "views/appointment_templates_appointments.xml",
        "views/appointment_templates_registration.xml",
        "views/appointment_templates_validation.xml",
        "views/website_pages_views.xml",
        "views/snippets/s_appointments.xml",
        "views/snippets/s_appointments_preview_data.xml",
        "views/snippets/s_online_appointment.xml",
        "security/ir.access.csv",
        "views/calendar_menus.xml",
    ],
    "demo": [
        "demo/appointment_demo.xml",
    ],
    "assets": {
        "web.assets_tests": [
            "website_appointment/static/tests/tours/*",
        ],
        "web.assets_unit_tests": [
            "website_appointment/static/tests/interactions/**/*",
        ],
        "web.assets_unit_tests_setup": [
            "website_appointment/static/src/snippets/**/*.js",
        ],
        "web.assets_frontend": [
            "website_appointment/static/src/scss/website_appointment.scss",
            "website_appointment/static/src/scss/website_appointment_editor.scss",
            "website_appointment/static/src/xml/website_appointment_templates.xml",
            "website_appointment/static/src/xml/appointment_no_slot.xml",
            "website_appointment/static/src/interactions/*.js",
            "website_appointment/static/src/snippets/**/*.js",
        ],
        "website.assets_editor": [
            "website_appointment/static/src/js/systray_items/*.js",
        ],
        "website.website_builder_assets": [
            "website_appointment/static/src/plugins/**/*",
        ],
    },
    "auto_install": [
        "calendar",
        "website_enterprise",
    ],
}
