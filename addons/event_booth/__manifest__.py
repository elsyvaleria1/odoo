{
    "name": "Event Booth Reservations",
    "version": "1.2",
    "oldest_upgradable_version": "1.2",
    "category": "Marketing/Events",
    "summary": "Define event booths, assign contacts and track reservations",
    "description": "Adds booth categories, event-type booth templates, availability counts and reservation confirmation with contact details. Booth sales and online booking require their respective extension modules; this addon provides the event booth records and reservation workflow.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "event",
    ],
    "data": [
        "security/ir.access.csv",
        "views/event_booth_category_views.xml",
        "views/event_type_booth_views.xml",
        "views/event_booth_views.xml",
        "views/event_type_views.xml",
        "views/event_event_views.xml",
        "views/event_menus.xml",
        "data/event_booth_category_data.xml",
        "data/mail_message_subtype_data.xml",
        "data/mail_templates.xml",
    ],
    "demo": [
        "demo/event_booth_demo.xml",
        "demo/event_type_demo.xml",
    ],
}
