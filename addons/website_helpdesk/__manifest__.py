{
    "name": "Website Help Center",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Services/Helpdesk",
    "sequence": 57,
    "summary": "Publish helpdesk team pages and accept website ticket submissions",
    "description": "Adds team website pages, ticket forms, attachment handling and help-center search hooks. Teams configure website visibility and enabled help content.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "helpdesk",
        "website",
    ],
    "data": [
        "data/helpdesk_data.xml",
        "views/helpdesk_views.xml",
        "views/helpdesk_templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "website_helpdesk/static/**/*",
            (
                "remove",
                "website_helpdesk/static/src/js/website_helpdesk_form_editor.js",
            ),
            (
                "remove",
                "website_helpdesk/static/src/js/website_helpdesk_edit_menu.js",
            ),
            (
                "remove",
                "website_helpdesk/static/tests/tours/**/*",
            ),
        ],
        "website.website_builder_assets": [
            "website_helpdesk/static/src/js/website_helpdesk_form_editor.js",
        ],
        "website.assets_editor": [
            "website_helpdesk/static/src/js/website_helpdesk_edit_menu.js",
        ],
        "web.assets_tests": [
            "website_helpdesk/static/tests/tours/**/*",
        ],
    },
    "auto_install": True,
    "post_init_hook": "_configure_teams",
    "uninstall_hook": "_restore_public_team_rule",
}
