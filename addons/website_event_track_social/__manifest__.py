{
    "name": "Event Talk Push Reminders",
    "version": "1.1",
    "category": "Marketing/Events",
    "sequence": 1021,
    "summary": "Schedule push reminders for visitors following event talks",
    "description": "Creates or updates reminder posts from talk settings and selects visitors subscribed to the relevant tracks. Requires website push messaging and visitor permission.",
    "author": "Odoo S.A.",
    "website": "https://www.odoo.com/app/events",
    "license": "Other OSI approved licence",
    "depends": [
        "website_event_social",
        "website_event_track",
    ],
    "data": [
        "views/event_track_views.xml",
    ],
    "auto_install": True,
    "post_init_hook": "post_init",
}
