{
    "name": "Course Forum Links",
    "version": "1.0",
    "category": "Website/eLearning",
    "summary": "Link course pages to forums and combine learner profile information",
    "description": "Adds forum associations and navigation to courses and adapts forum and learner profile views. Requires a configured course forum; course delivery, discussion moderation and membership behavior are supplied by the dependencies.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "website_slides",
        "website_forum",
    ],
    "data": [
        "security/ir.access.csv",
        "views/forum_forum_views.xml",
        "views/forum_post_views.xml",
        "views/res_config_settings_views.xml",
        "views/slide_channel_views.xml",
        "views/website_slides_menu_views.xml",
        "views/forum_forum_templates.xml",
        "views/website_slides_templates.xml",
    ],
    "demo": [
        "demo/slide_channel_demo.xml",
    ],
    "assets": {
        "website.website_builder_assets": [
            "website_slides_forum/static/src/website_builder/**/*",
        ],
    },
    "auto_install": True,
}
