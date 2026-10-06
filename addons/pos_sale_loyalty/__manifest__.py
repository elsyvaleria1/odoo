{
    "name": "POS Sales Order Reward Handling",
    "version": "1.0",
    "category": "Sales/Point of Sale",
    "sequence": 6,
    "summary": "Preserve sales reward quantities and exclude imported sales lines from POS loyalty points",
    "description": "Loads reward identifiers from sales order lines and adapts their import into POS. Imported sales lines do not earn POS loyalty points, and reward lines retain their sales quantities; program calculation belongs to the loyalty dependencies.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "pos_sale",
        "pos_loyalty",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_sale_loyalty/static/src/**/*",
        ],
        "web.assets_tests": [
            "pos_sale_loyalty/static/tests/tours/**/*",
        ],
    },
    "auto_install": True,
}
