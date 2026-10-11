{
    "name": "Help Center Forum Integration",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Services/Helpdesk",
    "sequence": 58,
    "summary": "Expose selected forums in help centers and link forum posts with tickets",
    "description": "Adds team forum configuration, help-center forum search and ticket-to-post or post-to-ticket actions. Requires the corresponding help-center feature and forum access; forum discussions and helpdesk workflow remain in their dependencies.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "website_forum",
        "website_helpdesk",
    ],
    "data": [
        "security/ir.access.csv",
        "views/forum_forum_templates.xml",
        "views/helpdesk_templates.xml",
        "views/helpdesk_views.xml",
        "views/forum_forum_views.xml",
        "wizards/wizard_helpdesk_ticket_create_forum_post_views.xml",
    ],
    "demo": [
        "demo/helpdesk_demo.xml",
        "demo/website_helpdesk_forum_demo.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "website_helpdesk_forum/static/src/interactions/**/*",
            "website_helpdesk_forum/static/src/components/**/*",
        ],
        "web.assets_tests": [
            "website_helpdesk_forum/static/tests/tours/**/*",
        ],
    },
    "auto_install": True,
}
