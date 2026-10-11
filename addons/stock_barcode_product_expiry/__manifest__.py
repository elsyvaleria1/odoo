{
    "name": "Inventory Barcode Expiration Dates",
    "version": "1.0",
    "category": "Supply Chain/Inventory",
    "summary": "Load product and lot expiration fields into inventory barcode operations",
    "description": "Extend barcode data for products, lots and stock move lines with expiration information. Adds the associated move-line view fields.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "stock_barcode",
        "product_expiry",
    ],
    "data": [
        "views/stock_move_line_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "stock_barcode_product_expiry/static/src/**/*",
        ],
        "web.assets_tests": [
            "stock_barcode_product_expiry/static/tests/tours/**/*",
        ],
        "web.assets_unit_tests": [
            "stock_barcode_product_expiry/static/tests/**/*",
            (
                "remove",
                "stock_barcode_product_expiry/static/tests/tours/**/*",
            ),
        ],
    },
    "auto_install": True,
}
