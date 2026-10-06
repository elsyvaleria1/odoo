{
    "name": "POS Percentage Discounts",
    "version": "1.0",
    "category": "Sales/Point of Sale",
    "sequence": 6,
    "summary": "Apply a percentage discount to eligible point-of-sale order lines",
    "description": "Adds a discount control and configured discount product to POS orders. Cashier input is limited to a percentage between zero and one hundred; the POS discount implementation creates discount lines using the applicable tax groups. Requires the discount feature and product configuration.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "point_of_sale",
    ],
    "data": [
        "data/pos_discount_data.xml",
        "views/res_config_settings_views.xml",
        "views/pos_config_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_discount/static/src/**/*",
        ],
        "web.assets_tests": [
            "pos_discount/static/tests/tours/**/*",
        ],
        "web.assets_unit_tests": [
            "pos_discount/static/tests/unit/**/*",
        ],
    },
}
