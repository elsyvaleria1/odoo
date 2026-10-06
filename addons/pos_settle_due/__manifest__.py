{
    "name": "POS Customer Balance Settlement",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Sales/Point of Sale",
    "sequence": 6,
    "summary": "Settle customer invoice and POS balances at the point of sale",
    "description": "Loads customer amounts due, adds settlement and deposit products and reconciles the resulting payments against linked balances.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "point_of_sale",
        "account_followup",
    ],
    "data": [
        "views/pos_order_views.xml",
        "views/account_move_views.xml",
        "data/pos_settle_due_data.xml",
    ],
    "assets": {
        "web.assets_unit_tests": [
            "pos_settle_due/static/tests/unit/**/*",
        ],
        "point_of_sale._assets_pos": [
            "pos_settle_due/static/src/**/*",
        ],
        "web.assets_tests": [
            "pos_settle_due/static/tests/tours/**/*",
        ],
    },
    "auto_install": True,
}
