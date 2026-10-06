{
    "name": "Inventory Barcode Lookup",
    "category": "Supply Chain/Inventory",
    "summary": "Look up unknown product barcodes from the inventory barcode interface",
    "description": "Expose Barcode Lookup product creation in the warehouse barcode flow. Requires the Barcode Lookup service configuration and API key.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "product_barcodelookup",
        "stock_barcode",
    ],
    "data": [
        "views/product_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "stock_barcode_barcodelookup/static/src/**/*.js",
            "stock_barcode_barcodelookup/static/src/**/*.xml",
        ],
        "web.assets_tests": [
            "stock_barcode_barcodelookup/static/tests/tours/**/*",
        ],
    },
}
