{
    "name": "Event Speaker Email Campaigns",
    "version": "1.0",
    "category": "Marketing/Email Marketing",
    "summary": "Create email campaigns targeting event track speakers",
    "description": "Add a speaker mailing action to events. Build campaign recipient filters from the event's track speakers.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "website_event_track",
        "mass_mailing",
    ],
    "data": [
        "views/event_views.xml",
    ],
    "auto_install": True,
}
