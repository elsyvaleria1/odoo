{
    "name": "Restaurant Adyen Tips",
    "version": "1.0",
    "category": "Sales/Point of Sale",
    "sequence": 6,
    "summary": "Capture restaurant payments with Adyen tip adjustments",
    "description": "Extends restaurant payment handling with Adyen tip updates, capture requests and payment notifications. Requires the Adyen terminal configuration and merchant account.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "pos_adyen",
        "pos_restaurant",
        "payment_adyen",
    ],
    "data": [
        "views/pos_payment_method_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_restaurant_adyen/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "pos_restaurant_adyen/static/tests/unit/data/**/*",
        ],
    },
    "auto_install": True,
}
