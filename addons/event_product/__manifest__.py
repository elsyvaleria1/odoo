{
    "name": "Event Ticket Products",
    "version": "1.0",
    "category": "Marketing/Events",
    "summary": "Configure products and prices for event tickets",
    "description": "Link event ticket definitions to products and calculate ticket pricing. Validates product service tracking used by event ticket flows.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "event",
        "product",
        "account",
    ],
    "data": [
        "views/event_ticket_views.xml",
        "views/event_registration_views.xml",
        "data/event_product_data.xml",
    ],
    "demo": [
        "demo/event_product_demo.xml",
        "demo/event_demo.xml",
    ],
    "auto_install": True,
}
