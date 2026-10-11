{
    "name": "Rental Inventory Transfers",
    "version": "1.0",
    "category": "Sales/Sales",
    "summary": "Track rental reservations, pickups and returns in inventory",
    "description": "Adds rental stock locations, availability calculations, serial-number reservations and pickup and return operations. Stock-transfer behavior depends on the rental picking configuration.",
    "author": "Odoo S.A.",
    "website": "https://www.odoo.com",
    "license": "Other OSI approved licence",
    "depends": [
        "sale_renting",
        "sale_stock",
    ],
    "data": [
        "security/sale_stock_renting_security.xml",
        "data/rental_stock_data.xml",
        "wizards/wizard_sale_order_pickup_return_views.xml",
        "wizards/wizard_stock_picking_return_views.xml",
        "reports/rental_report_views.xml",
        "reports/rental_order_report_templates.xml",
        "views/res_config_settings_views.xml",
        "views/sale_order_views.xml",
        "views/sale_order_line_views.xml",
        "views/product_template_views.xml",
        "views/res_company_views.xml",
        "views/product_trace_views.xml",
    ],
    "demo": [
        "demo/rental_stock_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "sale_stock_renting/static/src/**/*",
        ],
    },
    "auto_install": True,
    "post_init_hook": "_sync_rental_stock_moves",
}
