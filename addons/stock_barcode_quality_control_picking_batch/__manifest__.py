{
    "name": "Batch Barcode Quality Data",
    "version": "1.0",
    "category": "Supply Chain/Inventory",
    "summary": "Load batch-transfer quality fields in the barcode interface",
    "description": "Extend the stock picking batch fields returned to the barcode client. Uses the batch quality controls supplied by the dependent modules.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "quality_control_picking_batch",
        "stock_barcode_quality_control",
    ],
    "assets": {
        "web.assets_backend": [
            "stock_barcode_quality_control_picking_batch/static/**/*",
        ],
    },
    "auto_install": True,
}
