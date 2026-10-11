{
    "name": "Online Event Ticketing",
    "category": "Website/Website",
    "summary": "Add paid event registrations to the eCommerce checkout",
    "description": "Connects website event registration forms to sales tickets and shopping carts. Creates attendee information from registration submissions and adds ticket-specific cart and payment checks. Requires configured events, ticket products and the eCommerce payment setup used for paid orders.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "website_event",
        "event_sale",
        "website_sale",
    ],
    "data": [
        "reports/event_sale_report_views.xml",
        "views/event_event_views.xml",
        "views/website_event_templates.xml",
        "views/website_sale_templates.xml",
    ],
    "assets": {
        "web.assets_tests": [
            "website_event_sale/static/tests/**/*",
        ],
        "web.assets_frontend": [
            "website_event_sale/static/src/scss/*.scss",
        ],
    },
    "auto_install": True,
}
