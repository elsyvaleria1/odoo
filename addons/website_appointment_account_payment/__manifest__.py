{
    "name": "Website Appointment Payment Views",
    "version": "1.0",
    "category": "Services/Appointment",
    "summary": "Display booking prices and render appointment payment pages in the website layout",
    "description": "Adapts paid appointment cards, checkout and booking summaries for the website layout and navigation. Price labels require a paid appointment type with a product; booking and payment processing come from Appointment Booking Payments.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "appointment_account_payment",
        "website_enterprise",
        "website_appointment",
    ],
    "data": [
        "views/appointment_templates_appointments.xml",
        "views/appointment_templates_payment.xml",
        "views/calendar_booking_templates.xml",
    ],
    "demo": [
        "demo/appointment_demo.xml",
    ],
    "auto_install": True,
}
