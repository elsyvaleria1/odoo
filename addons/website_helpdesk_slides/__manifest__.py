{
    "name": "Help Center Course Content",
    "category": "Services/Helpdesk",
    "sequence": 58,
    "summary": "Include configured courses and lessons in help-center navigation and search",
    "description": "Adds course selections on helpdesk teams and help-center search adaptations for linked courses and lessons. Results follow team content selections and applicable website filters; course authoring and delivery are provided by eLearning.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "website_helpdesk",
        "website_slides",
    ],
    "data": [
        "views/helpdesk_views.xml",
        "views/helpdesk_templates.xml",
        "views/slide_channel_views.xml",
    ],
    "auto_install": True,
}
