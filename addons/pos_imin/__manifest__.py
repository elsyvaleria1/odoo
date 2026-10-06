{
    "name": "POS iMin Printer Integration",
    "version": "1.0",
    "category": "Sales/Point of Sale",
    "sequence": 6,
    "summary": "Print POS receipts through an available iMin printer service",
    "description": "Adds an iMin printer adapter and detection when the POS other-devices setting is enabled. Requires compatible hardware and its reachable printer service; receipt printing uses the bundled client library and can use an existing fallback printer when the iMin device is disconnected or off.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "point_of_sale",
    ],
    "data": [
        "views/pos_config_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_imin/static/lib/imin-printer/imin-printer.js",
            "pos_imin/static/src/**/*",
        ],
    },
}
