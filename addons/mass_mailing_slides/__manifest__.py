{
    "name": "Course Member Email Campaigns",
    "version": "1.0",
    "category": "Marketing/Email Marketing",
    "summary": "Create email campaigns for course participants",
    "description": "Add a mailing action to courses. Initialize campaign recipients from the selected course's members.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "website_slides",
        "mass_mailing",
    ],
    "data": [
        "views/slide_channel_views.xml",
    ],
    "auto_install": True,
}
