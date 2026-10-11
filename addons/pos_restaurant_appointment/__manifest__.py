{
    "name": "Restaurant Table Bookings",
    "version": "1.2",
    "oldest_upgradable_version": "1.2",
    "category": "Sales/Point of Sale",
    "sequence": 6,
    "summary": "Associate appointment resources with restaurant tables",
    "description": "Links restaurant tables to booking resources, loads booking data into the POS and notifies the POS when table bookings change.",
    "author": "Odoo S.A.",
    "website": "https://www.odoo.com/app/appointments",
    "license": "Other OSI approved licence",
    "depends": [
        "pos_restaurant",
        "pos_appointment",
    ],
    "data": [
        "views/resource_resource_views.xml",
        "views/pos_restaurant_views.xml",
        "views/calendar_event_views.xml",
    ],
    "demo": [
        "demo/pos_restaurant_appointment_demo.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_restaurant_appointment/static/src/**/*",
        ],
        "web.assets_backend": [
            "pos_restaurant_appointment/static/src/backend/json_field_resource/**/*",
        ],
        "web.assets_tests": [
            "pos_restaurant_appointment/static/tests/tours/**/*",
        ],
        "web.assets_unit_tests": [
            "pos_restaurant_appointment/static/tests/unit/**/*",
        ],
    },
    "auto_install": True,
    "post_init_hook": "_pos_restaurant_appointment_after_init",
}
