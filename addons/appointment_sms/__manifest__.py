{
    "name": "Appointment SMS Reminder Defaults",
    "version": "1.1",
    "category": "Services/Appointment",
    "sequence": 2150,
    "summary": "Add a one-hour SMS reminder default for new appointment types",
    "description": "Defines a calendar SMS alarm marked as a default for new appointment types and adds a phone-use notice to the booking form when SMS reminders are selected. Sending uses the Calendar SMS dependency and requires a usable recipient phone number and configured SMS service.",
    "author": "Odoo S.A.",
    "website": "https://www.odoo.com/app/appointments",
    "license": "OEEL-1",
    "depends": [
        "calendar",
        "calendar_sms",
    ],
    "data": [
        "data/calendar_data.xml",
        "views/appointment_templates_registration.xml",
    ],
    "demo": [
        "demo/appointment_demo.xml",
    ],
    "auto_install": True,
}
