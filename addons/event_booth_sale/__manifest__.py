{
    "name": "Event Booth Sales",
    "version": "1.5",
    "oldest_upgradable_version": "1.5",
    "category": "Marketing/Events",
    "summary": "Sell selected event booths through sales orders and track invoice payment",
    "description": "Links booth registrations to sales lines and requires booth selection before confirming lines configured for booth service tracking. Updates booth reservations on order confirmation and marks linked booths paid through the invoice payment hook; requires configured booth products and categories.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "event_booth",
        "event_sale",
    ],
    "data": [
        "security/ir.access.csv",
        "data/product_data.xml",
        "data/event_booth_category_data.xml",
        "views/sale_order_views.xml",
        "views/event_type_booth_views.xml",
        "views/event_booth_category_views.xml",
        "views/event_booth_registration_views.xml",
        "views/event_booth_views.xml",
        "wizards/wizard_sale_order_line_update_booth_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "event_booth_sale/static/src/**/*",
        ],
    },
    "auto_install": True,
}
