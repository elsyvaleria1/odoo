{
    "name": "Batch Transfer Barcode Operations",
    "version": "1.0",
    "category": "Supply Chain/Inventory",
    "summary": "Process transfer batches in the barcode interface",
    "description": "Adds batch creation, selection, confirmation and cancellation actions with shared barcode data for the included transfers.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "stock_barcode",
        "stock_picking_batch",
    ],
    "data": [
        "views/stock_barcode_picking.xml",
        "views/stock_barcode_picking_batch.xml",
        "views/stock_move_line_views.xml",
        "views/stock_package_type_views.xml",
        "wizards/wizard_stock_picking_cancel_views.xml",
        "data/data.xml",
    ],
    "demo": [
        "demo/stock_barcode_picking_batch_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "stock_barcode_picking_batch/static/src/**/*",
        ],
        "web.assets_tests": [
            "stock_barcode_picking_batch/static/tests/tours/**/*.js",
        ],
    },
    "auto_install": True,
}
