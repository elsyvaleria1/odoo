{
    "name": "Employee Resume Event Links",
    "version": "1.0",
    "category": "Hidden",
    "summary": "Link employee resume entries to onsite training events",
    "description": "Adds an onsite course type, an event reference, display defaults and training-related views for resume entries. This addon does not implement an event-completion hook that automatically creates resume entries.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "hr_skills",
        "event",
    ],
    "data": [
        "views/hr_resume_line_views.xml",
        "views/event_event_views.xml",
        "views/hr_skills_event_menus.xml",
    ],
    "auto_install": True,
}
