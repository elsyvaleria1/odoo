{
    "name": "Restaurant Preparation Courses",
    "version": "1.0.0",
    "category": "Sales/Point of Sale",
    "sequence": 7,
    "summary": "Display restaurant tables and courses on preparation screens",
    "description": "Adds restaurant table and course data to preparation orders and adapts order merging and display notifications.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "pos_restaurant",
        "pos_enterprise",
    ],
    "data": [
        "views/preparation_display_view.xml",
    ],
    "assets": {
        "pos_preparation_display.assets": [
            "pos_restaurant_preparation_display/static/src/app/**/*",
        ],
        "point_of_sale._assets_pos": [
            "pos_restaurant_preparation_display/static/src/override/**/*.js",
        ],
        "web.assets_tests": [
            "pos_restaurant_preparation_display/static/tests/tours/point_of_sale/**/*",
        ],
        "pos_preparation_display.assets_tour_tests": [
            "pos_restaurant_preparation_display/static/tests/tours/preparation_display/**/*",
        ],
    },
    "auto_install": True,
    "post_init_hook": "_pos_restaurant_preparation_display_post_init",
}
