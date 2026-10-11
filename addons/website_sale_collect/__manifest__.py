{
    "name": "Website Click and Collect",
    "version": "1.1",
    "category": "Website/Website",
    "summary": "Offer store pickup and location-based stock availability at online checkout",
    "description": "Configure in-store delivery methods and their warehouses. Select pickup locations and compatible payment options when a customer checks out.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "geocoding",
        "payment_custom",
        "website_sale_stock",
    ],
    "data": [
        "data/payment_method_data.xml",
        "data/payment_provider_data.xml",
        "data/product_product_data.xml",
        "data/delivery_carrier_data.xml",
        "views/delivery_carrier_views.xml",
        "views/delivery_form_templates.xml",
        "views/res_config_settings_views.xml",
        "views/stock_picking_views.xml",
        "views/stock_warehouse_views.xml",
        "views/templates.xml",
    ],
    "demo": [
        "demo/demo.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "website_sale_collect/static/src/**/*",
        ],
        "web.assets_tests": [
            "website_sale_collect/static/tests/tours/**/*",
        ],
    },
    "post_init_hook": "post_init_hook",
    "uninstall_hook": "uninstall_hook",
}
