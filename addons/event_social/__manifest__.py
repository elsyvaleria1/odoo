{
    "name": "Event Social Post Scheduling",
    "version": "1.0",
    "category": "Marketing/Social Marketing",
    "summary": "Schedule social posts from event communication templates",
    "description": "Adds social-post templates to event communication scheduling and creates posts for connected template accounts. Social posts cannot use registration-triggered scheduling; account connectivity and publication are provided by the Social dependency.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "event",
        "social",
    ],
    "data": [
        "security/ir.access.csv",
    ],
    "assets": {
        "web.assets_backend": [
            "event_social/static/src/template_reference_field/field_event_mail_template_reference.xml",
        ],
    },
    "auto_install": True,
}
