{
    "name": "Calendar SMS Reminders",
    "version": "1.1",
    "category": "Productivity/Calendar",
    "summary": "Send event reminders by text message",
    "description": "Adds SMS alarm types and message templates to calendar events. Reminder delivery uses the configured SMS service and its account requirements.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "calendar",
        "sms",
    ],
    "data": [
        "data/sms_data.xml",
        "views/calendar_views.xml",
    ],
    "auto_install": True,
}
