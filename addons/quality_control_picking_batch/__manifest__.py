{
    "name": "Batch Transfer Quality Checks",
    "version": "1.0",
    "category": "Supply Chain/Quality",
    "summary": "Perform quality checks for batch stock transfers",
    "description": "Links checks to transfer batches, shows pending checks on batches and adapts check handling when transfers are split into waves.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "quality_control",
        "stock_picking_batch",
    ],
    "data": [
        "views/stock_picking_batch_views.xml",
    ],
    "auto_install": True,
}
