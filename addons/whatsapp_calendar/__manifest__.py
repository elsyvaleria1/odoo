{
    "name": "WhatsApp Calendar Reminders",
    "version": "1.0",
    "category": "Productivity/WhatsApp",
    "summary": "Send calendar reminders using WhatsApp templates",
    "description": "Adds a WhatsApp alarm type and sends reminders through the configured template and responsible account.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "calendar",
        "whatsapp",
    ],
    "data": [
        "views/calendar_alarm_views.xml",
    ],
    "auto_install": True,
}
