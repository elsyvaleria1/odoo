{
    "name": "POS Barcode Product Lookup",
    "version": "1.0",
    "category": "Sales/Point of Sale",
    "summary": "Look up products from scanned barcodes in the POS",
    "description": "Adds POS frontend support for the Barcode Lookup product-creation integration. Requires its configured API key and service access.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "point_of_sale",
        "product_barcodelookup",
    ],
    "data": [
        "views/product_view.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "product_barcodelookup/static/src/widgets/**/*",
            "pos_barcodelookup/static/src/**/*",
        ],
        "web.assets_tests": [
            "pos_barcodelookup/static/tests/**/*",
        ],
    },
    "auto_install": True,
}
