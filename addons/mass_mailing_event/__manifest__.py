{
    "name": "Event Attendee Email Campaigns",
    "version": "1.0",
    "category": "Marketing/Email Marketing",
    "summary": "Create email campaigns targeting event attendees",
    "description": "Add event actions for mailing attendees and inviting contacts. Populate campaign recipient filters from event registration information.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "event",
        "mass_mailing",
    ],
    "data": [
        "views/event_views.xml",
    ],
    "auto_install": True,
}
