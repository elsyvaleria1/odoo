{
    "name": "Website Event Booth Checkout",
    "version": "1.0",
    "category": "Marketing/Events",
    "summary": "Add selected event booths to the website sales checkout",
    "description": "Connects booth registration to sales cart lines and adapts booth quantity and contact handling. Requires sale-enabled booth categories and products; ordering and payment processing are supplied by the event sales and eCommerce dependencies.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "event_booth_sale",
        "website_event_booth",
        "website_sale",
        "website_event_sale",
    ],
    "data": [
        "views/event_booth_registration_templates.xml",
        "views/event_booth_templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "/website_event_booth_sale/static/src/interactions/*",
        ],
        "web.assets_tests": [
            "/website_event_booth_sale/static/tests/tours/**/*.js",
        ],
    },
    "auto_install": True,
}
