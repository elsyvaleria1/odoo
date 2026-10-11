{
    "name": "Sold Booth Exhibitor Pages",
    "version": "1.0",
    "category": "Marketing/Events",
    "summary": "Link sold event booths to exhibitor website information",
    "description": "Connects booth sales with exhibitor records and their website presentation when the booth sale and exhibitor integrations are installed together.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "website_event_exhibitor",
        "website_event_booth_sale",
    ],
    "assets": {
        "web.assets_tests": [
            "website_event_booth_sale_exhibitor/static/tests/tours/website_event_booth_sale_exhibitor.js",
        ],
    },
    "auto_install": True,
}
