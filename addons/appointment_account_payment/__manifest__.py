{
    "name": "Appointment Booking Payments",
    "version": "1.2",
    "oldest_upgradable_version": "1.2",
    "category": "Services/Appointment",
    "summary": "Add payment checkout to configured paid appointment bookings",
    "description": "Creates an intermediate booking and draft invoice when an appointment type requires payment, then converts the booking to an event through the paid-booking flow. Requires a configured booking product and payment provider; pending or failed checkout remains a booking and availability is checked before event creation.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "calendar",
        "account_payment_provider",
    ],
    "data": [
        "data/product_data.xml",
        "security/ir.access.csv",
        "views/appointment_answer_input_views.xml",
        "views/appointment_templates_appointments.xml",
        "views/appointment_templates_payment.xml",
        "views/appointment_templates_registration.xml",
        "views/appointment_templates_validation.xml",
        "views/appointment_type_views.xml",
        "views/calendar_booking_templates.xml",
        "views/calendar_booking_views.xml",
    ],
    "demo": [
        "demo/product_demo.xml",
        "demo/appointment_demo.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "appointment_account_payment/static/src/scss/appointment_payment.scss",
        ],
    },
    "auto_install": True,
}
