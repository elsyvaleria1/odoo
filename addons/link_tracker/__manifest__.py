{
    "name": "Tracked Short Links",
    "version": "19.0.1.3",
    "oldest_upgradable_version": "19.0.1.3",
    "category": "Marketing",
    "summary": "Shorten URLs and use them to track clicks and UTMs",
    "description": "Create short URLs with campaign tracking parameters and record clicks on their redirects. Includes click statistics and scheduled cleanup of stored IP addresses.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "utm",
        "mail",
    ],
    "data": [
        "security/ir.access.csv",
        "data/ir_cron.xml",
        "views/link_tracker_views.xml",
        "views/utm_campaign_views.xml",
        "views/link_tracker_menus.xml",
    ],
}
