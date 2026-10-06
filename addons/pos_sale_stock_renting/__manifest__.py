{
    "name": "POS Rental Stock Transfers",
    "version": "1.0",
    "category": "Sales/Point of Sale",
    "sequence": 15,
    "summary": "Coordinate rental pickup quantities with POS order processing",
    "description": "Extends POS order processing and rental sale-line transferred quantities when rental stock operations are enabled.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "pos_sale",
        "sale_stock_renting",
    ],
    "assets": {
        "web.assets_tests": [
            "pos_sale_stock_renting/static/tests/**/*",
        ],
    },
    "auto_install": True,
}
