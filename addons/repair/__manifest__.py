{
    "name": "Repairs",
    "version": "1.4",
    "oldest_upgradable_version": "1.4",
    "category": "Supply Chain/Inventory",
    "sequence": 230,
    "summary": "Track repair orders, component movements and related sales",
    "description": "Provides repair orders with scheduling, warranty flags, technician notes and stock movements for added, removed or recycled components. Links repairs to sales orders and product traceability. Recorded repair completion updates the workflow and related movements; physical repair work remains a technician activity.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "sale_stock",
        "sale",
    ],
    "data": [
        "security/ir.access.csv",
        "wizards/wizard_repair_order_confirm_insufficient_stock_views.xml",
        "views/product_views.xml",
        "views/stock_move_views.xml",
        "views/repair_views.xml",
        "views/sale_order_views.xml",
        "views/product_trace_views.xml",
        "views/stock_picking_views.xml",
        "views/stock_warehouse_views.xml",
        "reports/repair_reports.xml",
        "reports/repair_templates_repair_order.xml",
        "data/repair_data.xml",
        "views/repair_menus.xml",
    ],
    "demo": [
        "demo/repair_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "repair/static/src/**/*",
        ],
        "web.assets_tests": [
            "repair/static/tests/tours/*.js",
        ],
    },
    "application": True,
    "post_init_hook": "_create_warehouse_data",
}
