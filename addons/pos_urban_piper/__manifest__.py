{
    "name": "UrbanPiper POS Orders",
    "version": "1.3",
    "oldest_upgradable_version": "1.3",
    "category": "Sales/Point of Sale",
    "summary": "Receive food-delivery platform orders through UrbanPiper",
    "description": "Process UrbanPiper webhooks into POS orders and synchronize configured stores and products. Requires an UrbanPiper account and configured service credentials.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "credential",
        "integration",
        "pos_enterprise",
        "pos_discount",
    ],
    "data": [
        "data/res_config_settings_data.xml",
        "data/pos_delivery_provider_data.xml",
        "data/product_product_data.xml",
        "security/ir.access.csv",
        "views/res_config_settings_views.xml",
        "views/pos_category_views.xml",
        "views/product_views.xml",
        "views/pos_payment_method_views.xml",
        "wizards/wizard_pos_config_simulate_urbanpiper_order_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_urban_piper/static/src/point_of_sale_overrirde/**/*",
            "pos_urban_piper/static/src/utils.js",
        ],
        "pos_preparation_display.assets": [
            "pos_urban_piper/static/src/pos_preparation_display_override/**/*",
        ],
        "web.assets_tests": [
            "pos_urban_piper/static/tests/tours/**/*",
        ],
        "web.assets_unit_tests": [
            "pos_urban_piper/static/tests/unit/**/*",
        ],
    },
    "post_init_hook": "_urban_piper_post_init",
}
