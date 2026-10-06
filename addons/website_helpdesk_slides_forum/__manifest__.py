{
    "name": "Helpdesk Course Forums",
    "category": "Services/Helpdesk",
    "summary": "Connect helpdesk website pages with course forums",
    "description": "Extend helpdesk website templates and forum template selection for the eLearning/forum combination. Uses the existing course and forum records.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "website_helpdesk",
        "website_slides_forum",
    ],
    "data": [
        "views/helpdesk_templates.xml",
    ],
    "auto_install": True,
}
