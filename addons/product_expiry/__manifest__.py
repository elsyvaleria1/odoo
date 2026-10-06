{
    "name": "Product Expiration Dates",
    "version": "1.3",
    "oldest_upgradable_version": "1.2",
    "category": "Supply Chain/Inventory",
    "summary": "Track lot expiration, removal and alert dates",
    "description": "Configure product shelf-life periods and compute the associated dates on lots. Includes alerts for lots reaching their configured warning dates.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "stock",
        "product_trace_expiry",
    ],
    "data": [
        "security/ir.access.csv",
        "security/stock_security.xml",
        "views/product_trace_views.xml",
        "views/product_category_views.xml",
        "views/product_template_views.xml",
        "views/res_config_settings_views.xml",
        "views/stock_move_views.xml",
        "views/stock_quant_views.xml",
        "wizards/wizard_stock_picking_validate_expired_views.xml",
        "reports/report_deliveryslip.xml",
        "reports/report_lot_barcode.xml",
        "data/product_expiry_data.xml",
    ],
    "assets": {
        "web.assets_tests": [
            "product_expiry/static/tests/tours/*.js",
        ],
        "web.assets_backend": [
            "product_expiry/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "product_expiry/static/tests/*.test.js",
        ],
    },
    "post_init_hook": "_enable_tracking_numbers",
}
