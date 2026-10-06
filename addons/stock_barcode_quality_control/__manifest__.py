{
    "name": "Barcode Transfer Quality Checks",
    "version": "1.0",
    "category": "Supply Chain/Inventory",
    "summary": "Open quality checks and refresh their results in barcode transfers",
    "description": "Connects barcode picking actions to transfer quality checks, including on-demand checks. Saves the current transfer before opening the quality action and refreshes line data afterwards; quality points, check types and transfer configuration come from the quality dependencies.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "stock_barcode",
        "quality_control",
    ],
    "assets": {
        "web.assets_backend": [
            "stock_barcode_quality_control/static/src/**/*.js",
            "stock_barcode_quality_control/static/src/**/*.xml",
        ],
        "web.assets_tests": [
            "stock_barcode_quality_control/static/tests/tours/**/*",
        ],
    },
    "auto_install": True,
}
