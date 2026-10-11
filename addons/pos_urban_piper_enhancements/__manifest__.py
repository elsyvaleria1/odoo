{
    "name": "UrbanPiper Store Hours and Scheduled Orders",
    "category": "Sales/Point of Sale",
    "summary": "Configure store hours and handle scheduled UrbanPiper deliveries",
    "description": "Extend UrbanPiper store data with opening times and product updates. Notify the POS of future deliveries and expose their preparation timing.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "pos_urban_piper",
    ],
    "data": [
        "data/ir_cron.xml",
        "data/pos_store_timing_data.xml",
        "security/pos_urban_piper_enhancements_security.xml",
        "security/ir.access.csv",
        "views/res_config_settings_views.xml",
        "views/pos_order_views.xml",
        "views/pos_store_time_views.xml",
        "views/report_invoice.xml",
        "views/product_attribute_views.xml",
        "views/pos_urban_piper_enhancements_menus.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_urban_piper_enhancements/static/src/point_of_sale_override/**/*",
        ],
        "pos_preparation_display.assets": [
            "pos_urban_piper_enhancements/static/src/pos_preparation_display_override/**/*",
            "pos_urban_piper/static/src/utils.js",
        ],
        "web.assets_unit_tests": [
            "pos_urban_piper_enhancements/static/tests/unit/**/*",
        ],
    },
    "auto_install": True,
}
