{
    "name": "Website Record Following",
    "version": "0.1",
    "category": "Website/Website",
    "summary": "Let website users subscribe to supported record discussions",
    "description": "Adds the website follow widget, subscription endpoints and follower-status checks. It uses the mail follower mechanism and the record access checks in those endpoints; other addons supply the pages and records where the widget appears.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "website",
        "mail",
    ],
    "data": [
        "views/website_mail_templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "website_mail/static/src/interactions/follow.js",
            "website_mail/static/src/css/website_mail.scss",
        ],
        "web.assets_inside_builder_iframe": [
            "website_mail/static/src/interactions/follow.edit.js",
        ],
        "web.assets_unit_tests_setup": [
            "website_mail/static/src/interactions/follow.js",
        ],
        "web.assets_unit_tests": [
            "website_mail/static/tests/**/*.test.js",
        ],
    },
    "auto_install": True,
}
