{
    "name": "Customer Ratings",
    "version": "1.6",
    "oldest_upgradable_version": "1.6",
    "category": "Productivity",
    "summary": "Collect customer scores and comments on business records",
    "description": "Provide rating records, feedback pages and links to the rated object. Applications use the rating mixin and templates to request and display feedback.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "mail",
    ],
    "data": [
        "views/rating_rating_views.xml",
        "views/rating_templates.xml",
        "views/mail_message_views.xml",
        "security/ir.access.csv",
        "views/rating_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "rating/static/src/core/common/**/*",
            "rating/static/src/core/web/**/*",
            "rating/static/src/scss/rating_rating_views.scss",
        ],
        "web.assets_frontend": [
            "rating/static/src/scss/rating_templates.scss",
        ],
        "web.assets_unit_tests": [
            "rating/static/tests/**/*",
        ],
        "mail.assets_public": [
            "rating/static/src/core/common/**/*",
        ],
        "portal.assets_chatter": [
            "rating/static/src/core/common/**/*",
        ],
    },
}
