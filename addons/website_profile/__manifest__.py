{
    "name": "Website User Profiles",
    "version": "1.0",
    "category": "Website/Website",
    "summary": "Display user profiles, badges and ranks with profile editing and email validation",
    "description": "Adds website profile pages, avatar and profile access checks, editable profile fields, gamification displays and email validation links. Visibility follows the configured website profile rules; profile statistics depend on records supplied by participating applications.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "website_partner",
        "gamification",
    ],
    "data": [
        "data/mail_template_data.xml",
        "views/gamification_badge_views.xml",
        "views/website_profile.xml",
        "views/website_views.xml",
        "security/ir.access.csv",
    ],
    "assets": {
        "web.assets_frontend": [
            "website_profile/static/src/scss/website_profile.scss",
            "website_profile/static/src/interactions/**/*",
            (
                "remove",
                "website_profile/static/src/interactions/**/*.edit.js",
            ),
        ],
        "website_profile.assets_profile_dialog": [
            (
                "include",
                "html_editor._assets_editor",
            ),
            "website_profile/static/src/components/**/*",
        ],
        "website.assets_inside_builder_iframe": [
            "website_profile/static/src/**/*.edit.js",
        ],
        "web.assets_tests": [
            "website_profile/static/tests/tours/tour_website_profile_description.js",
        ],
    },
    "esm": {
        "bundles": [
            "website_profile.assets_profile_dialog",
        ],
        "dynamic_children": {
            "web.assets_frontend": [
                "website_profile.assets_profile_dialog",
            ],
        },
    },
}
