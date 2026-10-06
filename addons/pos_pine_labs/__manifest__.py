{
    "name": "POS Pine Labs Terminals",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Sales/Point of Sale",
    "sequence": 6,
    "summary": "Request and track Pine Labs terminal payments for INR companies",
    "description": "Adds payment initiation, status polling and cancellation through the Pine Labs integration. Requires a configured merchant account, terminal credentials and a company whose currency is INR; payment instruments and terminal capabilities depend on the provider configuration.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "point_of_sale",
        "integration",
    ],
    "data": [
        "views/pos_payment_views.xml",
        "views/pos_payment_method_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_pine_labs/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "pos_pine_labs/static/tests/unit/data/**/*",
        ],
    },
}
