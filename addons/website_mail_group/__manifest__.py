{
    "name": "Website Mailing Groups",
    "version": "1.0",
    "category": "Website/Website",
    "summary": "Publish mailing-group discussions and subscription pages",
    "description": "Adds website routes and templates for group discussions and subscription management, using the group access and moderation settings.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "mail_group",
        "website",
    ],
    "data": [
        "views/snippets/s_group.xml",
        "views/snippets/snippets.xml",
        "views/mail_group_views.xml",
        "views/website_mail_group_menus.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "website_mail_group/static/src/snippets/**/*.js",
            (
                "remove",
                "website_mail_group/static/src/**/*.edit.js",
            ),
        ],
        "website.assets_inside_builder_iframe": [
            "website_mail_group/static/src/**/*.edit.js",
        ],
        "website.website_builder_assets": [
            "website_mail_group/static/src/website_builder/**/*",
        ],
    },
    "auto_install": True,
}
