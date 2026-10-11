{
    "name": "Manufacturing Barcode Operations",
    "version": "1.1",
    "category": "Supply Chain/Inventory",
    "summary": "Record manufacturing quantities and lots through barcode scanning",
    "description": "Adds barcode actions for production orders, component and by-product move lines, lot selection and partial-production handling.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "stock_barcode",
        "mrp",
    ],
    "data": [
        "security/ir_access.xml",
        "data/data.xml",
        "views/mrp_production.xml",
        "views/stock_move_line.xml",
        "views/stock_picking_type.xml",
        "views/res_config_settings_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "stock_barcode_mrp/static/src/**/*",
        ],
        "web.assets_tests": [
            "stock_barcode_mrp/static/tests/tours/**/*",
        ],
    },
    "auto_install": True,
}
