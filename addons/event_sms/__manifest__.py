{
    "name": "Event SMS Notifications",
    "version": "1.0",
    "category": "Marketing/Events",
    "summary": "Schedule text-message notifications for event attendees",
    "description": "Extend event communication schedules with SMS templates and delivery actions. Uses the SMS service configured for the application.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "event",
        "sms",
    ],
    "data": [
        "data/sms_data.xml",
        "security/ir.access.csv",
    ],
    "assets": {
        "web.assets_backend": [
            "event_sms/static/src/template_reference_field/*",
        ],
    },
    "auto_install": True,
}
