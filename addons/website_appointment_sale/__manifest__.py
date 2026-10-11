{
    "name": "Appointment eCommerce Checkout",
    "version": "1.0",
    "category": "Services/Appointment",
    "summary": "Add paid appointment bookings to the website sales cart",
    "description": "Replaces the paid-booking redirect with a sales cart line for the configured booking product and requested capacity, then opens checkout. Links orders, bookings and generated events; requires a paid appointment type and eCommerce payment configuration.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "website_appointment_account_payment",
        "website_sale",
    ],
    "data": [
        "views/appointment_templates_appointments.xml",
        "views/calendar_booking_views.xml",
        "views/calendar_event_views.xml",
        "views/sale_order_views.xml",
        "views/website_sale_templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "website_appointment_sale/static/src/scss/website_appointment_sale.scss",
            "website_appointment_sale/static/src/interactions/**/*",
        ],
    },
    "auto_install": True,
}
