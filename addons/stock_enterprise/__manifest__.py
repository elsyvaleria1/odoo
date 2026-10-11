{
    "name": "Inventory Maps and Cohorts",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Supply Chain/Inventory",
    "summary": "Review stock operations through maps and cohort reports",
    "description": "Adds transfer map views, stock-move views and cohort reporting to Inventory, with associated settings and frontend components.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "stock",
        "web_cohort",
        "web_map",
    ],
    "data": [
        "security/ir.access.csv",
        "views/res_config_settings_views.xml",
        "views/stock_move_views.xml",
        "views/stock_picking_map_views.xml",
        "reports/stock_report_views.xml",
        "views/stock_enterprise_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "stock_enterprise/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "stock_enterprise/static/tests/**/*",
        ],
    },
    "auto_install": [
        "stock",
    ],
}
