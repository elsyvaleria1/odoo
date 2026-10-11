{
    "name": "Website Link Tracking",
    "version": "1.0",
    "category": "Website/Website",
    "summary": "Create tracked links and view their statistics from the website",
    "description": "Add website pages for shortening links and displaying their click statistics. Uses the tracked-link records and redirect handling provided by Link Tracker.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "website",
        "link_tracker",
    ],
    "data": [
        "views/link_tracker_views.xml",
        "views/website_links_template.xml",
        "views/website_links_graphs.xml",
        "security/ir.access.csv",
        "views/website_links_menus.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "website_links/static/src/components/*.js",
            "website_links/static/src/interactions/*.js",
            "website_links/static/src/css/website_links.css",
            "website_links/static/src/xml/*.xml",
        ],
        "web.assets_tests": [
            "website_links/static/tests/**/*",
        ],
        "website.assets_editor": [
            "website_links/static/src/services/website_custom_menus.js",
        ],
    },
    "auto_install": True,
}
