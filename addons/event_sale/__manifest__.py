{
    "name": "Event Ticket Sales",
    "version": "1.5",
    "oldest_upgradable_version": "1.5",
    "category": "Marketing/Events",
    "summary": "Create event registrations from sales orders",
    "description": "Link ticket sales lines to event registrations and expose the related sales orders. Registration state and sale information follow the sales workflow.",
    "author": "Odoo S.A.",
    "website": "https://www.odoo.com/app/events",
    "license": "Other OSI approved licence",
    "depends": [
        "event_product",
        "sale",
        "sale_team",
    ],
    "data": [
        "views/event_registration_views.xml",
        "views/event_views.xml",
        "views/product_template_views.xml",
        "views/sale_order_views.xml",
        "data/event_sale_data.xml",
        "data/mail_templates.xml",
        "reports/event_sale_report_views.xml",
        "security/ir.access.csv",
        "security/event_security.xml",
        "wizards/wizard_sale_order_update_attendee_views.xml",
        "wizards/wizard_sale_order_line_update_event_views.xml",
        "views/event_sale_menus.xml",
    ],
    "demo": [
        "demo/event_sale_demo.xml",
        "demo/event_registration_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "event_sale/static/src/**/*",
        ],
        "web.assets_tests": [
            "event_sale/static/tests/tours/**/*",
        ],
    },
    "auto_install": True,
}
