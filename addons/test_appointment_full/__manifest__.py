{
    "name": "Appointment Full Tests",
    "version": "1.0",
    "category": "Hidden/Tests",
    "sequence": 9999,
    "summary": "Test Appointment Full behaviour, including performance, notifications",
    "description": "Run regression tests for Appointment Full. Loaded test suites include ``OnelineWAppointmentPerformance``, ``TestAppointmentNotificationsMail``, ``TestSyncOdoo2GoogleMail``, ``TestAppointmentNotificationsMicrosoftCalendar``.",
    "author": "Odoo S.A.",
    "website": "https://www.odoo.com/app/appointments",
    "license": "OEEL-1",
    "depends": [
        "appointment_crm",
        "appointment_hr",
        "calendar_google",
        "calendar_microsoft",
        "website_appointment",
    ],
}
