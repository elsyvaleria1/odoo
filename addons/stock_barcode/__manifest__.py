{
    "name": "Inventory Barcode Operations",
    "version": "1.4",
    "oldest_upgradable_version": "1.2",
    "category": "Supply Chain/Inventory",
    "sequence": 255,
    "summary": "Use barcode scanners to process logistics operations",
    "description": """
This module enables the barcode scanning feature for the warehouse management system.
    """,
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "stock",
        "web_tour",
        "web_mobile",
    ],
    "data": [
        "security/ir.access.csv",
        "security/ir_access.xml",
        "views/stock_inventory_views.xml",
        "views/stock_picking_views.xml",
        "views/stock_picking_type_views.xml",
        "views/stock_move_line_views.xml",
        "views/stock_barcode_views.xml",
        "views/res_config_settings_views.xml",
        "views/stock_scrap_views.xml",
        "views/stock_location_views.xml",
        "wizards/wizard_stock_picking_cancel_views.xml",
        "wizards/wizard_stock_picking_validate_partial_views.xml",
        "data/data.xml",
        "views/stock_barcode_menus.xml",
    ],
    "demo": [
        "demo/demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "stock_barcode/static/src/**/*.js",
            "stock_barcode/static/src/**/*.scss",
            "stock_barcode/static/src/**/*.xml",
        ],
        "web.assets_unit_tests": [
            "stock_barcode/static/tests/units/*.test.js",
        ],
        "web.assets_tests": [
            "stock_barcode/static/tests/tours/**/*",
        ],
    },
    "application": True,
    "auto_install": True,
}
