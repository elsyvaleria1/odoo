{
    "name": "Manufacturing Barcode Quality Data",
    "version": "1.0",
    "category": "Supply Chain/Inventory",
    "summary": "Load manufacturing quality fields in the barcode interface",
    "description": "Extend manufacturing-order data returned to the barcode client. Uses the manufacturing quality workflow supplied by its dependencies.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "stock_barcode",
        "quality_mrp",
    ],
    "assets": {
        "web.assets_backend": [
            "stock_barcode_quality_mrp/static/src/**/*",
        ],
        "web.assets_tests": [
            "stock_barcode_quality_mrp/static/tests/tours/**/*",
        ],
    },
    "auto_install": True,
}
