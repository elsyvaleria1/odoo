{
    "name": "POS AvaTax Calculation",
    "version": "1.0",
    "category": "Sales/Point of Sale",
    "summary": "Request external tax calculations for eligible POS orders through AvaTax",
    "description": "Adds POS line and address preparation, external-tax requests and returned tax data for POS. Requires configured AvaTax service access and a usable location or customer address; eligibility and order state determine when external taxes are applied.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "point_of_sale",
        "account_avatax",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_avatax/static/src/**/*",
        ],
        "web.assets_tests": [
            "pos_avatax/static/tests/tours/**/*",
        ],
    },
    "auto_install": [
        "point_of_sale",
        "account_avatax",
    ],
}
