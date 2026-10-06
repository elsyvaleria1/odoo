{
    "name": "WhatsApp-Website-Events",
    "category": "Marketing/Events",
    "summary": "Schedule WhatsApp notifications for event registrations",
    "description": "Add WhatsApp templates to event communication schedules and send them for matching registrations. Requires a configured WhatsApp business account and usable message templates.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "event",
        "whatsapp",
    ],
    "data": [
        "data/whatsapp_template_data.xml",
    ],
    "demo": [
        "demo/event_mail_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "whatsapp_event/static/src/template_reference_field/field_event_mail_template_reference.xml",
        ],
    },
    "auto_install": True,
}
