{
    "name": "Field Service Material Stock Operations",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Services/Field Service",
    "summary": "Process stock deliveries and lot assignments for billable field service tasks",
    "description": "Connects task sales lines to stock moves, material pickup and lot or serial assignment. The delivery flow operates on billable tasks with a sales order and checks quantity-decrease exceptions before completing moves; warehouse, route and tracking configuration determine the stock operations.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "industry_fsm_sale",
        "sale_stock",
    ],
    "data": [
        "security/ir.access.csv",
        "views/project_task_views.xml",
        "views/stock_move_views.xml",
        "wizards/wizard_project_task_update_product_lot_views.xml",
        "views/product_product_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "industry_fsm_stock/static/src/**/*",
        ],
        "web.assets_tests": [
            "industry_fsm_stock/static/tests/tours/**/*",
        ],
        "web.assets_unit_tests": [
            "industry_fsm_stock/static/tests/product_catalog.test.js",
        ],
    },
    "auto_install": True,
}
