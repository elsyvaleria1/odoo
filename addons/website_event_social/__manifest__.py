{
    "name": "Event Push Notifications",
    "version": "1.1",
    "category": "Marketing/Events",
    "sequence": 1020,
    "summary": "Send push messages to subscribed event attendees",
    "description": "Adds event actions for push posts and reminders and connects event registrations to eligible visitor subscriptions. Requires configured website push messaging and recipient subscriptions.",
    "author": "Odoo S.A.",
    "website": "https://www.odoo.com/app/events",
    "license": "OEEL-1",
    "depends": [
        "website_event",
        "social_push_notifications",
    ],
    "data": [
        "views/event_event_views.xml",
        "views/event_templates_registration.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "website_event_social/static/**/*",
        ],
    },
    "auto_install": True,
}
