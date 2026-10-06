{
    "name": "Barcode Lookup Products",
    "version": "1.2",
    "oldest_upgradable_version": "1.2",
    "category": "Sales/Sales",
    "summary": "Create or update products from the Barcode Lookup service",
    "description": "Look up product information and images using scanned or entered barcodes. Requires a Barcode Lookup API key and service availability.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "credential",
        "product",
    ],
    "data": [
        "security/ir.access.csv",
        "data/ir_cron_data.xml",
        "data/product_data.xml",
        "views/product_product_views.xml",
        "views/res_config_settings_views.xml",
        "wizards/wizard_product_product_update_image_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "product_barcodelookup/static/src/**/*",
        ],
    },
    "auto_install": True,
}
