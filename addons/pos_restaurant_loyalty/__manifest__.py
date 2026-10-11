{
    "name": "Restaurant POS Reward Updates",
    "version": "1.0",
    "category": "Sales/Point of Sale",
    "sequence": 6,
    "summary": "Refresh rewards on table selection and assign reward lines to the last course",
    "description": "Extends restaurant POS order handling to recompute rewards after a table is selected. When an order has courses, newly generated reward lines receive its last course; loyalty programs are configured in the dependency.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "pos_restaurant",
        "pos_loyalty",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_restaurant_loyalty/static/src/**/*",
        ],
        "web.assets_tests": [
            "pos_restaurant_loyalty/static/tests/tours/**/*",
        ],
    },
    "auto_install": True,
}
