{
    "name": "Batch and Wave Transfers",
    "version": "1.3",
    "oldest_upgradable_version": "1.3",
    "category": "Supply Chain/Inventory",
    "summary": "Group stock transfers into batches and picking waves",
    "description": "Create batches and waves of stock operations and assign their transfers. Includes grouping and processing actions for warehouse picking workflows.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "stock",
    ],
    "data": [
        "security/res_groups.xml",
        "security/ir.access.csv",
        "views/stock_picking_batch_views.xml",
        "views/stock_picking_type_views.xml",
        "views/stock_move_line_views.xml",
        "views/stock_picking_wave_views.xml",
        "views/stock_picking_views.xml",
        "wizards/wizard_stock_picking_add_to_batch_views.xml",
        "wizards/wizard_stock_move_line_add_to_wave_views.xml",
        "reports/stock_picking_batch_report_views.xml",
        "reports/report_picking_batch.xml",
        "views/stock_picking_batch_menus.xml",
    ],
    "demo": [
        "demo/stock_picking_batch_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "stock_picking_batch/static/src/js/stock_picking_many2many_field.js",
            "stock_picking_batch/static/src/scss/*.scss",
        ],
        "web.assets_tests": [
            "stock_picking_batch/static/tests/tours/**/*",
        ],
    },
}
