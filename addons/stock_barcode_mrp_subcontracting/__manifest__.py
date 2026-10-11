{
    "name": "Barcode Subcontracting Details",
    "version": "1.0",
    "category": "Supply Chain/Inventory",
    "summary": "Open subcontracting component details from eligible barcode transfer lines",
    "description": "Adds a component-details action to subcontracting lines in the barcode picking interface. It saves the current transfer before opening the stock move action and hides the action for done or cancelled lines; subcontracting processing comes from the dependent modules.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "stock_barcode",
        "mrp_subcontracting",
    ],
    "assets": {
        "web.assets_backend": [
            "stock_barcode_mrp_subcontracting/static/src/**/*.js",
            "stock_barcode_mrp_subcontracting/static/src/**/*.xml",
        ],
        "web.assets_tests": [
            "stock_barcode_mrp_subcontracting/static/tests/tours/**/*.js",
        ],
    },
    "auto_install": True,
}
